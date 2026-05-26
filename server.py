"""
Menteso Virtual Office — Web Server
FastAPI backend serving the agent dashboard and API endpoints.
"""
import sys
import os
import json
import asyncio
import queue
import threading
import shutil
import secrets
import time
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, UploadFile, File, Body
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from shared.agent_registry import discover_agents, get_agent_runner
from shared.memory import load_memory
from shared.social_publishing import publish_article_to_social, social_status_snapshot
from agents.pct_agent.scraper import fetch_wipo_gazettes_async
from agents.patentzoom_seo_agent import get_dashboard_data as get_seo_dashboard_data

app = FastAPI(title="Menteso Virtual Office")
RUN_CONTROLS = {}
GOOGLE_OAUTH_STATES = {}
SEO_SCHEDULER_THREAD = None
SEO_SCHEDULER_STOP = threading.Event()
SEO_BROWSER_LOCK = threading.Lock()
SEO_BROWSER_SESSION_THREAD = None
SEO_BROWSER_PROCESS = None
SEO_CHROME_DEBUG_PORT = 9222
SEO_WORKSPACE_PROPERTY_KEYS = {
    "patentzoom": "GOOGLE_SEARCH_CONSOLE_PROPERTY",
    "patent-drawing-experts": "PATENT_DRAWING_EXPERTS_GOOGLE_SEARCH_CONSOLE_PROPERTY",
    "ip-docketers": "IP_DOCKETERS_GOOGLE_SEARCH_CONSOLE_PROPERTY",
    "menteso": "MENTESO_GOOGLE_SEARCH_CONSOLE_PROPERTY",
}
SEO_WORKSPACE_AUTO_PUBLISH_KEYS = {
    "patentzoom": "AUTO_PUBLISH",
    "patent-drawing-experts": "PATENT_DRAWING_EXPERTS_AUTO_PUBLISH",
    "ip-docketers": "IP_DOCKETERS_AUTO_PUBLISH",
    "menteso": "MENTESO_AUTO_PUBLISH",
}


def _get_run_status(name: str):
    control = RUN_CONTROLS.get(name)
    if not control:
        return {"status": "idle"}

    thread = control.get("thread")
    stop_event = control.get("stop_event")
    if thread and thread.is_alive():
        return {
            "status": "stopping" if stop_event and stop_event.is_set() else "running",
        }

    RUN_CONTROLS.pop(name, None)
    return {"status": "idle"}

# Directories
PROJECT_DIR = Path(__file__).parent
STATIC_DIR = PROJECT_DIR / "static"
UPLOADS_DIR = PROJECT_DIR / "uploads"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
WIPO_GAZETTES_CACHE = STATIC_DIR / "wipo_gazettes_cache.json"
SEO_INDEXING_STATE_FILE = PROJECT_DIR / "agents" / "patentzoom_seo_agent" / "state" / "indexing-status.json"
SEO_SCHEDULER_STATE_FILE = PROJECT_DIR / "agents" / "patentzoom_seo_agent" / "state" / "scheduler-state.json"
SEO_BROWSER_PROFILE_DIR = PROJECT_DIR / "agents" / "patentzoom_seo_agent" / "runtime" / "browser" / "google-search-console"
ENV_FILE = PROJECT_DIR / ".env"
UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def startup_event():
    _ensure_local_seo_scheduler()


@app.on_event("shutdown")
async def shutdown_event():
    SEO_SCHEDULER_STOP.set()


def _read_wipo_gazettes_cache():
    if not WIPO_GAZETTES_CACHE.exists():
        return []
    try:
        with open(WIPO_GAZETTES_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        options = data.get("options", [])
        return options if isinstance(options, list) else []
    except Exception:
        return []


def _write_wipo_gazettes_cache(options):
    payload = {"options": options}
    with open(WIPO_GAZETTES_CACHE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def _load_env_map():
    data = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                value = value[1:-1]
            data[key.strip()] = value
    return data


def _resolve_seo_workspace_id(workspace_id: str | None):
    key = str(workspace_id or "patentzoom").strip().lower() or "patentzoom"
    return key if key in SEO_WORKSPACE_PROPERTY_KEYS else "patentzoom"


def _workspace_property_env_key(workspace_id: str | None):
    return SEO_WORKSPACE_PROPERTY_KEYS[_resolve_seo_workspace_id(workspace_id)]


def _workspace_auto_publish_env_key(workspace_id: str | None):
    return SEO_WORKSPACE_AUTO_PUBLISH_KEYS[_resolve_seo_workspace_id(workspace_id)]


def _seo_workspace_state_paths(workspace_id: str | None = None):
    key = _resolve_seo_workspace_id(workspace_id)
    base = PROJECT_DIR / "agents" / "patentzoom_seo_agent"
    if key == "patentzoom":
        state_dir = base / "state"
        runtime_dir = base / "runtime"
    else:
        state_dir = base / "state" / "workspaces" / key
        runtime_dir = base / "runtime" / "workspaces" / key
    return {
        "generated_posts": state_dir / "generated-posts.json",
        "indexing_status": state_dir / "indexing-status.json",
        "social_status": state_dir / "social-posting-status.json",
        "scheduler_state": state_dir / "scheduler-state.json",
        "runtime_dir": runtime_dir,
    }


def _format_env_value(value):
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if any(ch in text for ch in [" ", "#", "'", '"']) or "\n" in text:
        return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"
    return text


def _write_env_updates(updates: dict):
    existing_lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    handled = set()
    new_lines = []

    for line in existing_lines:
        if "=" not in line or line.strip().startswith("#"):
            new_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in updates:
            new_lines.append(f"{key}={_format_env_value(updates[key])}")
            handled.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in handled:
            new_lines.append(f"{key}={_format_env_value(value)}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _google_oauth_redirect_uri():
    return "http://127.0.0.1:8000/api/google/search-console/callback"


def _google_search_console_status(workspace_id: str | None = None):
    env = _load_env_map()
    client_id = str(env.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = str(env.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    refresh_token = str(env.get("GOOGLE_OAUTH_REFRESH_TOKEN") or "").strip()
    property_key = _workspace_property_env_key(workspace_id)
    property_name = str(env.get(property_key) or env.get("GOOGLE_SEARCH_CONSOLE_PROPERTY") or "").strip()
    return {
        "connected": bool(refresh_token and client_id and client_secret),
        "clientConfigured": bool(client_id and client_secret),
        "property": property_name,
        "redirectUri": _google_oauth_redirect_uri(),
        "scope": "https://www.googleapis.com/auth/webmasters",
    }


def _load_seo_indexing_statuses(workspace_id: str | None = None):
    path = _seo_workspace_state_paths(workspace_id)["indexing_status"]
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        urls = payload.get("urls", {})
        return urls if isinstance(urls, dict) else {}
    except Exception:
        return {}


def _save_seo_indexing_status(status: dict, workspace_id: str | None = None):
    path = _seo_workspace_state_paths(workspace_id)["indexing_status"]
    payload = {"urls": _load_seo_indexing_statuses(workspace_id)}
    payload["urls"][status["postUrl"]] = status
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_seo_scheduler_state(workspace_id: str | None = None):
    path = _seo_workspace_state_paths(workspace_id)["scheduler_state"]
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save_seo_scheduler_state(updates: dict, workspace_id: str | None = None):
    path = _seo_workspace_state_paths(workspace_id)["scheduler_state"]
    state = _load_seo_scheduler_state(workspace_id)
    state.update(updates or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def _is_truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_seo_publish_time(raw_value: str):
    value = str(raw_value or "").strip()
    if not value:
        return 7, 0
    token = value.split()[0]
    parts = token.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        return 7, 0
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return hour, minute


def _load_seo_generated_posts(workspace_id: str | None = None):
    state_path = _seo_workspace_state_paths(workspace_id)["generated_posts"]
    if not state_path.exists():
        return []
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        items = payload.get("generatedPosts", [])
        return items if isinstance(items, list) else []
    except Exception:
        return []


def _has_published_seo_post_for_date(date_iso: str, workspace_id: str | None = None):
    for item in _load_seo_generated_posts(workspace_id):
        if str(item.get("date", "")).strip() == str(date_iso) and str(item.get("status", "")).strip().lower() == "publish":
            return True
    return False


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ist_now():
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def _discover_indexing_sitemaps(base_url: str):
    base = str(base_url or "").rstrip("/")
    fallbacks = [
        f"{base}/sitemap_index.xml",
        f"{base}/post-sitemap.xml",
        f"{base}/sitemap.xml",
    ]
    if not base:
        return fallbacks

    candidates = []
    try:
        robots = requests.get(f"{base}/robots.txt", timeout=20)
        if robots.ok:
            for line in robots.text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("sitemap:"):
                    sitemap_url = stripped.split(":", 1)[1].strip()
                    if sitemap_url:
                        candidates.append(sitemap_url)
    except Exception:
        pass

    candidates.extend(fallbacks)
    ranked = []
    seen = set()
    priority = {
        f"{base}/sitemap_index.xml": 0,
        f"{base}/post-sitemap.xml": 1,
        f"{base}/news-sitemap.xml": 2,
        f"{base}/sitemap.xml": 3,
    }
    for url in sorted(candidates, key=lambda item: priority.get(item, 10)):
        if url not in seen:
            ranked.append(url)
            seen.add(url)
    return ranked


def _search_console_inspect_url(property_name: str, url: str):
    property_part = requests.utils.quote(property_name, safe="")
    url_part = requests.utils.quote(url, safe="")
    return f"https://search.google.com/search-console/inspect?resource_id={property_part}&id={url_part}"


def _prepare_google_browser_profile():
    SEO_BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    local_state = SEO_BROWSER_PROFILE_DIR / "Local State"
    default_profile = SEO_BROWSER_PROFILE_DIR / "Default"
    if local_state.exists() and default_profile.exists():
        return

    source_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    source_local_state = source_root / "Local State"
    source_default = source_root / "Default"
    try:
        if source_local_state.exists() and not local_state.exists():
            shutil.copy2(source_local_state, local_state)
        if source_default.exists() and not default_profile.exists():
            shutil.copytree(source_default, default_profile, dirs_exist_ok=True)
    except Exception:
        pass


def _chrome_executable():
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def _chrome_debug_endpoint():
    return f"http://127.0.0.1:{SEO_CHROME_DEBUG_PORT}"


def _chrome_debug_ready():
    try:
        response = requests.get(f"{_chrome_debug_endpoint()}/json/version", timeout=3)
        return response.ok
    except Exception:
        return False


def _request_indexing_via_browser(url: str, property_name: str):
    property_home_url = f"https://search.google.com/search-console?resource_id={requests.utils.quote(property_name, safe='')}"
    inspect_url = property_home_url
    session_result = _launch_google_browser_session(property_name)
    if not _chrome_debug_ready():
        return {
            "attempted": True,
            "submitted": False,
            "status": "login_required",
            "message": session_result.get("message") or "Open the Google browser session, sign in once, and retry.",
            "inspectUrl": inspect_url,
        }

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except Exception as exc:
        return {
            "attempted": False,
            "submitted": False,
            "status": "unavailable",
            "message": f"Playwright is unavailable: {exc}",
            "inspectUrl": inspect_url,
        }

    with SEO_BROWSER_LOCK:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(_chrome_debug_endpoint())
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(property_home_url, wait_until="domcontentloaded", timeout=120000)
                page.wait_for_timeout(5000)

                lower_url = page.url.lower()
                if "accounts.google.com" in lower_url or "servicelogin" in lower_url:
                    return {
                        "attempted": True,
                        "submitted": False,
                        "status": "login_required",
                        "message": "Google login is still required in the browser session. Sign in in the opened Chrome window once, then retry.",
                        "inspectUrl": inspect_url,
                    }

                for selector in [
                    "text=/verify it.?s you/i",
                    "text=/challenge/i",
                    "text=/confirm it.?s you/i",
                ]:
                    if page.locator(selector).count():
                        return {
                            "attempted": True,
                            "submitted": False,
                            "status": "challenge_required",
                            "message": "Google requested an additional verification step in the connected Chrome session.",
                            "inspectUrl": inspect_url,
                        }

                inspect_input = page.locator('input[role="combobox"][aria-label*="Inspect any URL"]').first
                try:
                    inspect_input.wait_for(state="visible", timeout=30000)
                except PlaywrightTimeoutError:
                    return {
                        "attempted": True,
                        "submitted": False,
                        "status": "search_box_not_found",
                        "message": "The Search Console URL inspection box was not available in the connected Chrome session.",
                        "inspectUrl": inspect_url,
                    }

                inspect_input.click(force=True, timeout=15000)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.keyboard.insert_text(url)
                page.keyboard.press("Enter")

                try:
                    page.wait_for_url(re.compile(r"https://search\.google\.com/search-console/inspect\?"), timeout=45000)
                except PlaywrightTimeoutError:
                    pass
                page.wait_for_timeout(8000)
                inspect_url = page.url

                clicked = False
                for locator in [
                    page.get_by_role("button", name=re.compile(r"request indexing", re.I)),
                    page.get_by_text(re.compile(r"request indexing", re.I)),
                    page.locator("text=/REQUEST INDEXING/i"),
                ]:
                    try:
                        if locator.count():
                            locator.first.click(timeout=15000, force=True)
                            clicked = True
                            break
                    except Exception:
                        continue

                if not clicked:
                    return {
                        "attempted": True,
                        "submitted": False,
                        "status": "button_not_found",
                        "message": "The Request Indexing action was not available on the Search Console inspection page.",
                        "inspectUrl": inspect_url,
                    }

                success_message = "Request Indexing was clicked in Google Search Console."
                success_patterns = [
                    "text=/indexing requested/i",
                    "text=/request again/i",
                    "text=/priority crawl queue/i",
                    "text=/request submitted/i",
                    "text=/live test started/i",
                ]
                try:
                    page.wait_for_selector(", ".join(success_patterns), timeout=45000)
                    for pattern in success_patterns:
                        locator = page.locator(pattern)
                        if locator.count():
                            try:
                                success_message = locator.first.inner_text(timeout=5000).strip() or success_message
                            except Exception:
                                pass
                            break
                except PlaywrightTimeoutError:
                    pass

                return {
                    "attempted": True,
                    "submitted": True,
                    "status": "requested",
                    "message": success_message,
                    "inspectUrl": inspect_url,
                }
        except Exception as exc:
            return {
                "attempted": True,
                "submitted": False,
                "status": "failed",
                "message": str(exc),
                "inspectUrl": inspect_url,
            }


def _launch_google_browser_session(property_name: str):
    global SEO_BROWSER_PROCESS
    if _chrome_debug_ready():
        return {
            "launched": False,
            "message": "Google browser session is already open. Use the existing Chrome window to confirm the Search Console account is signed in.",
        }

    _prepare_google_browser_profile()
    chrome_path = _chrome_executable()
    if not chrome_path:
        return {
            "launched": False,
            "message": "Google Chrome was not found on this machine.",
        }

    args = [
        chrome_path,
        f"--remote-debugging-port={SEO_CHROME_DEBUG_PORT}",
        f"--user-data-dir={SEO_BROWSER_PROFILE_DIR}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        f"https://search.google.com/search-console?resource_id={requests.utils.quote(property_name, safe='')}",
    ]
    try:
        SEO_BROWSER_PROCESS = subprocess.Popen(args)
    except Exception as exc:
        return {
            "launched": False,
            "message": f"Could not start Google Chrome debug session: {exc}",
        }

    for _ in range(20):
        if _chrome_debug_ready():
            return {
                "launched": True,
                "message": "Google browser session opened. Sign in once in the visible Chrome window if needed, then future Request Indexing clicks can run automatically.",
            }
        time.sleep(1)

    return {
        "launched": True,
        "message": "Chrome was launched, but the debug endpoint is still warming up. Wait a few seconds and retry if needed.",
    }


def _get_google_oauth_access_token(workspace_id: str | None = None):
    env = _load_env_map()
    client_id = str(env.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = str(env.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    refresh_token = str(env.get("GOOGLE_OAUTH_REFRESH_TOKEN") or "").strip()
    if not client_id or not client_secret or not refresh_token:
        raise ValueError("Google Search Console OAuth is not configured.")

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    property_key = _workspace_property_env_key(workspace_id)
    property_name = str(env.get(property_key) or env.get("GOOGLE_SEARCH_CONSOLE_PROPERTY") or "").strip()
    return payload.get("access_token", ""), property_name


def _verify_url_indexable(url: str):
    issues = []
    try:
        response = requests.get(url, timeout=30, allow_redirects=True)
        if not response.ok:
            issues.append(f"Page returned HTTP {response.status_code}")
            return False, issues
        if "noindex" in str(response.headers.get("X-Robots-Tag") or "").lower():
            issues.append("X-Robots-Tag contains noindex")
        html = response.text or ""
        if 'name="robots"' in html.lower() and "noindex" in html.lower():
            if "content=" in html.lower():
                issues.append("Meta robots contains noindex")
    except Exception as exc:
        issues.append(f"Could not fetch published URL: {exc}")
    return len(issues) == 0, issues


def _submit_sitemaps_to_search_console(access_token: str, property_name: str, sitemap_urls):
    submitted = []
    headers = {"Authorization": f"Bearer {access_token}"}
    property_path = requests.utils.quote(property_name, safe="")
    for sitemap_url in sitemap_urls:
        try:
            uri = f"https://www.googleapis.com/webmasters/v3/sites/{property_path}/sitemaps/{requests.utils.quote(sitemap_url, safe='')}"
            response = requests.put(uri, headers=headers, timeout=30)
            if response.ok:
                submitted.append(sitemap_url)
        except Exception:
            continue
    return submitted


def _inspect_url_in_search_console(access_token: str, property_name: str, url: str):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
        headers=headers,
        json={"inspectionUrl": url, "siteUrl": property_name},
        timeout=45,
    )
    if not response.ok:
        return None, response.text
    payload = response.json()
    result = ((payload or {}).get("inspectionResult") or {}).get("indexStatusResult") or {}
    return {
        "verdict": str(result.get("verdict") or ""),
        "coverageState": str(result.get("coverageState") or ""),
        "indexingState": str(result.get("indexingState") or ""),
        "lastCrawlTime": str(result.get("lastCrawlTime") or ""),
        "referringUrls": list(result.get("referringUrls") or [])[:10],
        "sitemaps": list(result.get("sitemaps") or [])[:10],
    }, ""


def _run_manual_indexing_request(url: str, workspace_id: str | None = None):
    env = _load_env_map()
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}".rstrip("/") if parsed_url.scheme and parsed_url.netloc else str(env.get("WP_BASE_URL") or "").rstrip("/")
    property_key = _workspace_property_env_key(workspace_id)
    property_name = str(env.get(property_key) or env.get("GOOGLE_SEARCH_CONSOLE_PROPERTY") or "").strip()
    access_token = ""
    oauth_error = ""
    try:
        access_token, property_name = _get_google_oauth_access_token(workspace_id)
    except Exception as exc:
        oauth_error = str(exc)
    sitemap_candidates = _discover_indexing_sitemaps(base_url)
    primary_sitemaps = sitemap_candidates[:2]
    pinged = []
    for sitemap_url in primary_sitemaps:
        try:
            requests.get(f"https://www.google.com/ping?sitemap={requests.utils.quote(sitemap_url, safe='')}", timeout=20)
            pinged.append(sitemap_url)
        except Exception:
            continue

    submitted = _submit_sitemaps_to_search_console(access_token, property_name, primary_sitemaps) if access_token else []
    indexable, issues = _verify_url_indexable(url)
    inspection, inspect_error = _inspect_url_in_search_console(access_token, property_name, url) if access_token else (None, "")
    browser_fallback = None
    indexed_now = str((inspection or {}).get("coverageState") or "").lower().startswith("submitted and indexed") or str(
        (inspection or {}).get("coverageState") or ""
    ).lower().startswith("indexed")
    if indexable and not indexed_now:
        browser_fallback = _request_indexing_via_browser(url, property_name)

    status = {
        "postUrl": url,
        "source": "manual",
        "indexable": indexable,
        "indexabilityIssues": issues,
        "sitemapCandidates": sitemap_candidates,
        "sitemapPinged": pinged,
        "searchConsoleSitemapsSubmitted": submitted,
        "indexingApiAttempted": False,
        "indexingApiSubmitted": False,
        "autoSubmitSucceeded": bool(submitted),
        "inspected": bool(inspection),
        "inspection": inspection,
        "browserFallbackAttempted": bool(browser_fallback and browser_fallback.get("attempted")),
        "browserFallbackSubmitted": bool(browser_fallback and browser_fallback.get("submitted")),
        "browserFallbackStatus": (browser_fallback or {}).get("status", ""),
        "browserFallbackMessage": (browser_fallback or {}).get("message", ""),
        "browserFallbackInspectUrl": (browser_fallback or {}).get("inspectUrl", ""),
        "requestCompletedAt": _now_iso(),
        "error": inspect_error if inspect_error else oauth_error,
    }
    _save_seo_indexing_status(status, workspace_id)
    return status


def _launch_agent_run(name: str, input_data: dict | None = None, emit=None, on_complete=None):
    agents = discover_agents()
    agent = next((a for a in agents if a["module_name"] == name), None)
    if not agent:
        return {"ok": False, "response": JSONResponse({"error": "Agent not found"}, status_code=404)}

    payload = dict(input_data or {})

    status = _get_run_status(name)
    if status["status"] != "idle":
        msg = "Agent is stopping, please wait" if status["status"] == "stopping" else "Agent is already running"
        return {"ok": False, "response": JSONResponse({"error": msg, "status": status["status"]}, status_code=409)}

    stop_event = threading.Event()
    control = {"stop_event": stop_event, "thread": None, "interruptors": []}
    payload["stop_requested"] = stop_event.is_set

    def register_stop_handler(handler):
        if callable(handler):
            control["interruptors"].append(handler)

    payload["register_stop_handler"] = register_stop_handler

    def worker():
        completion = None
        try:
            runner = get_agent_runner(name)
            result = runner(input_data=payload or None, on_step=emit)
            completion = {"type": "complete", "result": result}
            if emit:
                emit(completion)
        except Exception as e:
            completion = {"type": "error", "message": str(e)}
            if emit:
                emit(completion)
        finally:
            RUN_CONTROLS.pop(name, None)
            if callable(on_complete):
                try:
                    on_complete(completion or {"type": "error", "message": "Agent finished without a completion payload"})
                except Exception:
                    pass
            if emit:
                emit(None)

    thread = threading.Thread(target=worker, daemon=True)
    control["thread"] = thread
    RUN_CONTROLS[name] = control
    thread.start()
    return {"ok": True, "control": control}


def _seo_scheduler_completion_handler(event: dict):
    result = event.get("result", {}) if isinstance(event, dict) else {}
    status = str(result.get("status") or event.get("type") or "unknown")
    workspace_id = result.get("workspaceId") or "patentzoom"
    _save_seo_scheduler_state(
        {
            "last_auto_finished_at": _now_iso(),
            "last_auto_result_status": status,
            "last_auto_post_status": str(result.get("postStatus") or ""),
            "last_auto_topic": str(result.get("topic") or result.get("title") or ""),
            "last_auto_wordpress_url": str(result.get("wordpressUrl") or ""),
            "last_auto_error": str(result.get("error") or event.get("message") or ""),
        },
        workspace_id,
    )
    _maybe_auto_request_indexing_after_publish(result, source="scheduler")
    _maybe_auto_share_to_social_after_publish(result, source="scheduler")


def _should_auto_request_indexing(result: dict):
    if not isinstance(result, dict):
        return False
    if str(result.get("status") or "").strip().lower() != "success":
        return False
    if str(result.get("postStatus") or "").strip().lower() != "publish":
        return False
    return bool(str(result.get("wordpressUrl") or "").strip())


def _maybe_auto_request_indexing_after_publish(result: dict, source: str = "run"):
    if not _should_auto_request_indexing(result):
        return False

    url = str(result.get("wordpressUrl") or "").strip()
    if not url:
        return False
    workspace_id = result.get("workspaceId") or "patentzoom"

    def worker():
        try:
            status = _run_manual_indexing_request(url, workspace_id)
            if source == "scheduler":
                _save_seo_scheduler_state(
                    {
                        "last_auto_indexing_requested_at": _now_iso(),
                        "last_auto_indexing_status": str(status.get("browserFallbackStatus") or status.get("inspection", {}).get("coverageState") or ""),
                        "last_auto_indexing_url": url,
                        "last_auto_indexing_error": str(status.get("error") or ""),
                    },
                    workspace_id,
                )
        except Exception as exc:
            if source == "scheduler":
                _save_seo_scheduler_state(
                    {
                        "last_auto_indexing_requested_at": _now_iso(),
                        "last_auto_indexing_status": "failed",
                        "last_auto_indexing_url": url,
                        "last_auto_indexing_error": str(exc),
                    },
                    workspace_id,
                )

    threading.Thread(
        target=worker,
        daemon=True,
        name=f"seo-indexing-{int(time.time())}",
    ).start()
    return True


def _social_status_for_workspace(workspace_id: str | None = None):
    return social_status_snapshot(
        _resolve_seo_workspace_id(workspace_id),
        _load_env_map(),
        _seo_workspace_state_paths(workspace_id)["social_status"],
    )


def _should_auto_share_to_social(result: dict):
    if not _should_auto_request_indexing(result):
        return False
    workspace_id = result.get("workspaceId") or "patentzoom"
    status = _social_status_for_workspace(workspace_id)
    return bool(status.get("autoPostEnabled")) and int(status.get("configuredPlatformCount") or 0) > 0


def _maybe_auto_share_to_social_after_publish(result: dict, source: str = "run"):
    if not _should_auto_share_to_social(result):
        return False

    workspace_id = result.get("workspaceId") or "patentzoom"
    env = _load_env_map()
    state_path = _seo_workspace_state_paths(workspace_id)["social_status"]

    def worker():
        try:
            social_result = publish_article_to_social(workspace_id, result, env, state_path=state_path)
            if source == "scheduler":
                ok = bool(social_result.get("ok"))
                _save_seo_scheduler_state(
                    {
                        "last_auto_social_posted_at": _now_iso(),
                        "last_auto_social_status": "posted" if ok else "failed",
                        "last_auto_social_url": str(social_result.get("articleUrl") or ""),
                        "last_auto_social_error": " | ".join(social_result.get("errors") or []),
                    },
                    workspace_id,
                )
        except Exception as exc:
            if source == "scheduler":
                _save_seo_scheduler_state(
                    {
                        "last_auto_social_posted_at": _now_iso(),
                        "last_auto_social_status": "failed",
                        "last_auto_social_url": str(result.get("wordpressUrl") or ""),
                        "last_auto_social_error": str(exc),
                    },
                    workspace_id,
                )

    threading.Thread(
        target=worker,
        daemon=True,
        name=f"seo-social-{int(time.time())}",
    ).start()
    return True


def _maybe_schedule_daily_seo_run_for_workspace(workspace_id: str | None = None):
    workspace_id = _resolve_seo_workspace_id(workspace_id)
    env = _load_env_map()
    if not _is_truthy(env.get(_workspace_auto_publish_env_key(workspace_id))):
        return

    now_ist = _ist_now()
    today_iso = now_ist.strftime("%Y-%m-%d")
    publish_hour, publish_minute = _parse_seo_publish_time(env.get("SEO_AUTO_PUBLISH_TIME", "07:00 IST"))
    scheduled_minutes = publish_hour * 60 + publish_minute
    current_minutes = now_ist.hour * 60 + now_ist.minute

    if current_minutes < scheduled_minutes:
        return

    if _has_published_seo_post_for_date(today_iso, workspace_id):
        _save_seo_scheduler_state(
            {
                "last_checked_at": _now_iso(),
                "last_skip_reason": "Published SEO article already exists for today.",
                "last_skip_date": today_iso,
            },
            workspace_id,
        )
        return

    state = _load_seo_scheduler_state(workspace_id)
    if str(state.get("last_auto_attempt_date") or "").strip() == today_iso:
        return

    launch_result = _launch_agent_run(
        "patentzoom_seo_agent",
        {
            "workspace_id": workspace_id,
            "publish_override": "publish",
            "enable_featured_image": True,
            "dry_run": False,
            "scheduled_run": True,
        },
        emit=None,
        on_complete=_seo_scheduler_completion_handler,
    )
    if not launch_result.get("ok"):
        _save_seo_scheduler_state(
            {
                "last_checked_at": _now_iso(),
                "last_skip_reason": "Scheduler could not start the SEO agent because it was not idle.",
                "last_skip_date": today_iso,
            },
            workspace_id,
        )
        return

    _save_seo_scheduler_state(
        {
            "last_checked_at": _now_iso(),
            "last_auto_attempt_date": today_iso,
            "last_auto_started_at": _now_iso(),
            "last_skip_reason": "",
            "last_auto_result_status": "running",
            "last_auto_post_status": "",
            "last_auto_error": "",
        },
        workspace_id,
    )


def _maybe_schedule_daily_seo_run():
    for workspace_id in SEO_WORKSPACE_AUTO_PUBLISH_KEYS:
        _maybe_schedule_daily_seo_run_for_workspace(workspace_id)


def _seo_scheduler_loop():
    while not SEO_SCHEDULER_STOP.is_set():
        try:
            _maybe_schedule_daily_seo_run()
        except Exception as exc:
            _save_seo_scheduler_state(
                {
                    "last_checked_at": _now_iso(),
                    "last_scheduler_error": str(exc),
                }
            )
        SEO_SCHEDULER_STOP.wait(45)


def _ensure_local_seo_scheduler():
    global SEO_SCHEDULER_THREAD
    if SEO_SCHEDULER_THREAD and SEO_SCHEDULER_THREAD.is_alive():
        return
    SEO_SCHEDULER_STOP.clear()
    SEO_SCHEDULER_THREAD = threading.Thread(target=_seo_scheduler_loop, daemon=True, name="seo-daily-scheduler")
    SEO_SCHEDULER_THREAD.start()


# ---------------------------------------------------------------------------
# Root — serve dashboard HTML
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = STATIC_DIR / "index.html"
    with open(html_path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# API — List agents
# ---------------------------------------------------------------------------
@app.get("/api/agents")
async def list_agents():
    agents = discover_agents()
    result = []
    for a in agents:
        module_name = a.get("module_name", "")
        memory = load_memory(module_name)
        result.append({
            **a,
            "stats": memory.get("stats", {}),
            "learning_count": len(memory.get("learnings", [])),
        })
    return result


# ---------------------------------------------------------------------------
# API — Agent detail
# ---------------------------------------------------------------------------
@app.get("/api/agents/{name}")
async def agent_detail(name: str):
    agents = discover_agents()
    agent = next((a for a in agents if a["module_name"] == name), None)
    if not agent:
        return JSONResponse({"error": "Agent not found"}, status_code=404)

    memory = load_memory(name)
    return {
        **agent,
        "memory": memory,
    }


@app.get("/api/agents/{name}/dashboard-data")
async def agent_dashboard_data(name: str, workspace_id: str = "patentzoom"):
    if name == "patentzoom_seo_agent":
        return get_seo_dashboard_data(workspace_id)
    return JSONResponse({"error": "Dashboard data is not available for this agent"}, status_code=404)


@app.get("/api/google/search-console/status")
async def google_search_console_status(workspace_id: str = "patentzoom"):
    return _google_search_console_status(workspace_id)


@app.get("/api/social/status")
async def social_status(workspace_id: str = "patentzoom"):
    return _social_status_for_workspace(workspace_id)


@app.post("/api/social/config")
async def social_config(payload: dict = Body(...)):
    workspace_id = _resolve_seo_workspace_id(payload.get("workspace_id") or payload.get("workspaceId"))
    prefix = {
        "patentzoom": "PATENTZOOM",
        "patent-drawing-experts": "PATENT_DRAWING_EXPERTS",
        "ip-docketers": "IP_DOCKETERS",
        "menteso": "MENTESO",
    }[workspace_id]

    updates = {}
    field_map = {
        "auto_post": f"{prefix}_SOCIAL_AUTO_POST",
        "platforms": f"{prefix}_SOCIAL_PLATFORMS",
        "facebook_page_id": f"{prefix}_SOCIAL_FACEBOOK_PAGE_ID",
        "meta_access_token": f"{prefix}_SOCIAL_META_ACCESS_TOKEN",
        "instagram_business_account_id": f"{prefix}_SOCIAL_INSTAGRAM_BUSINESS_ACCOUNT_ID",
        "linkedin_organization_urn": f"{prefix}_SOCIAL_LINKEDIN_ORGANIZATION_URN",
        "linkedin_access_token": f"{prefix}_SOCIAL_LINKEDIN_ACCESS_TOKEN",
    }

    for input_key, env_key in field_map.items():
        if input_key in payload:
            updates[env_key] = payload.get(input_key)

    if not updates:
        return JSONResponse({"error": "No social configuration values were provided."}, status_code=400)

    _write_env_updates(updates)
    return {"status": "saved", "social": _social_status_for_workspace(workspace_id)}


@app.post("/api/social/post-now")
async def social_post_now(payload: dict = Body(...)):
    workspace_id = _resolve_seo_workspace_id(payload.get("workspace_id") or payload.get("workspaceId"))
    url = str(payload.get("url") or payload.get("wordpressUrl") or "").strip()
    title = str(payload.get("title") or "").strip()
    primary_keyword = str(payload.get("primaryKeyword") or "").strip()
    article = payload.get("article") if isinstance(payload.get("article"), dict) else {}

    if not url:
        return JSONResponse({"error": "A published article URL is required."}, status_code=400)

    try:
        result = await asyncio.to_thread(
            publish_article_to_social,
            workspace_id,
            {
                "wordpressUrl": url,
                "title": title,
                "primaryKeyword": primary_keyword,
                "article": article,
                "excerpt": payload.get("excerpt") or article.get("excerpt") or "",
            },
            _load_env_map(),
            _seo_workspace_state_paths(workspace_id)["social_status"],
        )
        return {"status": "ok", "social": result}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/google/search-console/request-indexing")
async def google_search_console_request_indexing(payload: dict = Body(...)):
    url = str(payload.get("url") or "").strip()
    workspace_id = str(payload.get("workspace_id") or payload.get("workspaceId") or "patentzoom").strip() or "patentzoom"
    if not url:
        return JSONResponse({"error": "A published URL is required."}, status_code=400)

    try:
        status = await asyncio.to_thread(_run_manual_indexing_request, url, workspace_id)
        return {"status": "ok", "indexing": status}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/google/search-console/config")
async def google_search_console_config(payload: dict = Body(...)):
    client_id = str(payload.get("client_id") or "").strip()
    client_secret = str(payload.get("client_secret") or "").strip()
    workspace_id = _resolve_seo_workspace_id(payload.get("workspace_id") or payload.get("workspaceId"))
    property_name = str(payload.get("property") or "").strip()

    if not client_id or not client_secret:
        return JSONResponse({"error": "Google OAuth client ID and client secret are required"}, status_code=400)

    _write_env_updates(
        {
            "GOOGLE_OAUTH_CLIENT_ID": client_id,
            "GOOGLE_OAUTH_CLIENT_SECRET": client_secret,
            _workspace_property_env_key(workspace_id): property_name,
        }
    )
    return {"status": "saved", **_google_search_console_status(workspace_id)}


@app.post("/api/google/search-console/browser-session")
async def google_search_console_browser_session(workspace_id: str = "patentzoom"):
    env = _load_env_map()
    property_name = str(env.get(_workspace_property_env_key(workspace_id)) or env.get("GOOGLE_SEARCH_CONSOLE_PROPERTY") or "").strip()
    try:
        result = await asyncio.to_thread(_launch_google_browser_session, property_name)
        return {"status": "ok", **result}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/google/search-console/connect")
async def google_search_console_connect(workspace_id: str = "patentzoom"):
    env = _load_env_map()
    client_id = str(env.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = str(env.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        return JSONResponse(
            {"error": "Save GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET first."},
            status_code=400,
        )

    state = secrets.token_urlsafe(24)
    GOOGLE_OAUTH_STATES[state] = {"created_at": asyncio.get_event_loop().time(), "workspace_id": _resolve_seo_workspace_id(workspace_id)}
    params = {
        "client_id": client_id,
        "redirect_uri": _google_oauth_redirect_uri(),
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/webmasters",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@app.get("/api/google/search-console/callback", response_class=HTMLResponse)
async def google_search_console_callback(code: str = None, state: str = None, error: str = None):
    if error:
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>Google connection failed</h2><p>{error}</p><p><a href='http://127.0.0.1:8000/' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>",
            status_code=400,
        )

    if not code or not state or state not in GOOGLE_OAUTH_STATES:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>Google connection failed</h2><p>Missing or invalid OAuth callback state.</p><p><a href='http://127.0.0.1:8000/' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>",
            status_code=400,
        )

    oauth_state = GOOGLE_OAUTH_STATES.pop(state, None) or {}
    workspace_id = _resolve_seo_workspace_id(oauth_state.get("workspace_id"))
    env = _load_env_map()
    client_id = str(env.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = str(env.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": _google_oauth_redirect_uri(),
        },
        timeout=30,
    )
    if not token_response.ok:
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>Google connection failed</h2><pre style='white-space:pre-wrap'>{token_response.text}</pre><p><a href='http://127.0.0.1:8000/' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>",
            status_code=400,
        )

    token_data = token_response.json()
    updates = {
        "GOOGLE_OAUTH_ACCESS_TOKEN": token_data.get("access_token", ""),
        "GOOGLE_OAUTH_REFRESH_TOKEN": token_data.get("refresh_token", ""),
        "GOOGLE_OAUTH_TOKEN_EXPIRY": str(token_data.get("expires_in", "")),
    }
    _write_env_updates(updates)
    return HTMLResponse(
        "<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>Google Search Console connected</h2><p>You can close this tab and return to the Menteso SEO Posting Agent dashboard.</p><p><a href='http://127.0.0.1:8000/' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>"
    )


# ---------------------------------------------------------------------------
# API — Upload file for agent
# ---------------------------------------------------------------------------
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file (Excel, etc.) and return the saved path."""
    safe_name = file.filename.replace(" ", "_")
    save_path = UPLOADS_DIR / safe_name

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "filename": safe_name,
        "path": str(save_path),
        "size": len(content),
    }


# ---------------------------------------------------------------------------
# API — Download output file
# ---------------------------------------------------------------------------
@app.get("/api/download/{filename}")
async def download_file(filename: str):
    file_path = OUTPUTS_DIR / filename
    if not file_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(
        str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
# API — WIPO gazette options
# ---------------------------------------------------------------------------
@app.get("/api/wipo/gazettes")
async def list_wipo_gazettes():
    try:
        gazettes = await fetch_wipo_gazettes_async()
        _write_wipo_gazettes_cache(gazettes)
        return {"options": gazettes}
    except Exception as e:
        cached = _read_wipo_gazettes_cache()
        if cached:
            return {"options": cached, "cached": True}
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# API — Pipeline progress (for page refreshes during long runs)
# ---------------------------------------------------------------------------
@app.get("/api/agents/{name}/progress")
async def agent_progress(name: str):
    """Return current progress from the latest progress JSONL file."""
    import json as _json
    candidates = sorted(OUTPUTS_DIR.glob("pct_progress_*.jsonl"), reverse=True)
    if not candidates:
        return {"status": "no_progress"}
    path = candidates[0]
    try:
        meta = None
        completed = 0
        found = 0
        not_found = 0
        errors = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                obj = _json.loads(line.strip())
                if obj.get("_meta"):
                    meta = obj
                    continue
                completed += 1
                s = obj.get("status", "")
                if s == "found":
                    found += 1
                elif s == "not_found":
                    not_found += 1
                else:
                    errors += 1
        return {
            "status": "in_progress" if meta else "unknown",
            "file": path.name,
            "total": meta.get("total", 0) if meta else 0,
            "completed": completed,
            "found": found,
            "not_found": not_found,
            "errors": errors,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/agents/{name}/run-status")
async def agent_run_status(name: str):
    return _get_run_status(name)


def _start_agent_run(name: str, input_data: dict | None = None):
    msg_queue = queue.Queue()

    def emit(message):
        if message is None:
            msg_queue.put(None)
            return
        if isinstance(message, dict):
            msg_queue.put(json.dumps(message))
        else:
            msg_queue.put(json.dumps({"type": "step", "message": message}))

    def on_complete(event):
        if name == "patentzoom_seo_agent" and isinstance(event, dict):
            result = event.get("result", {}) if isinstance(event, dict) else {}
            _maybe_auto_request_indexing_after_publish(result, source="dashboard")
            _maybe_auto_share_to_social_after_publish(result, source="dashboard")

    launch = _launch_agent_run(name, input_data=input_data, emit=emit, on_complete=on_complete)
    if not launch.get("ok"):
        return launch["response"]

    async def event_stream():
        while True:
            try:
                msg = msg_queue.get(timeout=0.05)
            except queue.Empty:
                yield ": keepalive\n\n"
                await asyncio.sleep(0.05)
                continue
            if msg is None:
                break
            yield f"data: {msg}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# API — Run agent (SSE stream) — supports input_data via query params
# ---------------------------------------------------------------------------
@app.get("/api/agents/{name}/run")
async def run_agent_sse(
    name: str,
    file_path: str = None,
    mode: str = None,
    gazette: str = None,
):
    input_data = {}
    if file_path:
        input_data["file_path"] = file_path
    if mode:
        input_data["mode"] = mode
    if gazette:
        input_data["gazette"] = gazette
    return _start_agent_run(name, input_data)


@app.post("/api/agents/{name}/run")
async def run_agent_sse_post(name: str, payload: dict = Body(default=None)):
    return _start_agent_run(name, payload)


@app.post("/api/agents/{name}/stop")
async def stop_agent_run(name: str):
    control = RUN_CONTROLS.get(name)
    if not control or not control.get("thread") or not control["thread"].is_alive():
        return JSONResponse({"error": "Agent is not running"}, status_code=409)

    control["stop_event"].set()
    interrupt_sent = 0
    for interruptor in list(control.get("interruptors", [])):
        try:
            interruptor()
            interrupt_sent += 1
        except Exception:
            pass
    return {"status": "stop_requested", "interrupt_sent": interrupt_sent}


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
