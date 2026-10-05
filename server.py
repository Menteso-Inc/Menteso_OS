"""
Menteso Virtual Office — Web Server
FastAPI backend serving the agent dashboard and API endpoints.
"""
import sys
import os
import json
import asyncio
import ast
import queue
import threading
import shutil
import secrets
import hmac
import hashlib
import base64
import time
import re
import subprocess
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

sys.path.insert(0, os.path.dirname(__file__))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)
except Exception:
    pass

from fastapi import FastAPI, UploadFile, File, Body, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from shared.agent_registry import discover_agents, get_agent_runner
from shared import db_storage
from shared.email_notifications import send_pct_completion_email
from shared.memory import load_memory
from shared.social_publishing import publish_article_to_social, social_status_snapshot
from agents.pct_agent.scraper import fetch_wipo_gazettes_async
from agents.patentzoom_seo_agent import get_dashboard_data as get_seo_dashboard_data
from agents.accountant_agent import get_dashboard_data as get_accountant_dashboard_data

OVERDUE_REMINDER_STATUS_FILE = Path(os.getenv(
    "OVERDUE_REMINDER_STATUS_FILE", "/app/accountant-status/overdue-reminder-status.json"
))

def _payment_customer(token: str) -> tuple[dict, dict]:
    secret = os.getenv("INVOICE_REMINDER_PORTAL_SECRET", "")
    if len(secret) < 32:
        raise ValueError("Payment portal is not configured")
    body, supplied = token.split(".", 1)
    expected = base64.urlsafe_b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    if not hmac.compare_digest(supplied, expected):
        raise ValueError("Invalid or expired payment link")
    claim = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    if int(claim["exp"]) < int(time.time()):
        raise ValueError("Invalid or expired payment link")
    state = json.loads(OVERDUE_REMINDER_STATUS_FILE.read_text(encoding="utf-8-sig"))
    row = state.get("customers", {}).get(str(claim["customer_id"]))
    if not row or int(row.get("invoice_count", 0)) < 2:
        raise ValueError("No multi-invoice account was found")
    return state, row

app = FastAPI(title="Menteso Virtual Office")
RUN_CONTROLS = {}
RUN_LIVE_STATUS = {}
GOOGLE_OAUTH_STATES = {}
SEO_SCHEDULER_THREAD = None
SEO_SCHEDULER_STOP = threading.Event()
SEO_BROWSER_LOCK = threading.Lock()
SEO_BROWSER_SESSION_THREAD = None
SEO_BROWSER_PROCESS = None
SEO_DASHBOARD_CACHE = {}
SEO_DASHBOARD_CACHE_LOCK = threading.Lock()
SEO_DASHBOARD_CACHE_TTL_SECONDS = 60
SEO_CHROME_DEBUG_PORT = 9222
SEO_WORKSPACE_PROPERTY_KEYS = {
    "patent-drawing-experts": "PATENT_DRAWING_EXPERTS_GOOGLE_SEARCH_CONSOLE_PROPERTY",
    "ip-docketers": "IP_DOCKETERS_GOOGLE_SEARCH_CONSOLE_PROPERTY",
    "menteso": "MENTESO_GOOGLE_SEARCH_CONSOLE_PROPERTY",
}
SEO_WORKSPACE_AUTO_PUBLISH_KEYS = {
    "patent-drawing-experts": "PATENT_DRAWING_EXPERTS_AUTO_PUBLISH",
    "ip-docketers": "IP_DOCKETERS_AUTO_PUBLISH",
    "menteso": "MENTESO_AUTO_PUBLISH",
}


def _get_run_status(name: str):
    control = RUN_CONTROLS.get(name)
    live = RUN_LIVE_STATUS.get(name, {})
    if not control:
        return {"status": "idle", **live} if live else {"status": "idle"}

    thread = control.get("thread")
    stop_event = control.get("stop_event")
    if thread and thread.is_alive():
        return {
            "status": "stopping" if stop_event and stop_event.is_set() else "running",
            **live,
        }

    # Thread died without the worker's finally block clearing the entry —
    # treat that as a crashed run and self-heal so the UI can move on.
    RUN_CONTROLS.pop(name, None)
    return {"status": "idle", "recovered": True, **live}


def _append_live_log(snapshot: dict, message: str, event_type: str = "step"):
    logs = snapshot.setdefault("logs", [])
    logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": str(message),
        "type": event_type,
    })
    if len(logs) > 200:
        del logs[:-200]


def _update_live_status(name: str, event):
    snapshot = RUN_LIVE_STATUS.setdefault(name, {
        "logs": [],
        "metrics": {
            "totalRows": 0,
            "processedRows": 0,
            "foundRows": 0,
            "notFoundRows": 0,
            "errorRows": 0,
        },
        "browser": {},
        "updatedAt": _now_iso() if "_now_iso" in globals() else datetime.now(timezone.utc).isoformat(),
    })
    snapshot["updatedAt"] = _now_iso() if "_now_iso" in globals() else datetime.now(timezone.utc).isoformat()

    if not isinstance(event, dict):
        message = str(event)
        _append_live_log(snapshot, message)
        match = re.search(r"(?:Parsed|Ready to process)\s+(\d+)\s+patent", message, re.I)
        if match:
            snapshot["metrics"]["totalRows"] = int(match.group(1))
        return

    event_type = str(event.get("type") or "step")
    if event_type == "step":
        message = str(event.get("message") or "")
        if message:
            _append_live_log(snapshot, message)
            match = re.search(r"(?:Parsed|Ready to process)\s+(\d+)\s+patent", message, re.I)
            if match:
                snapshot["metrics"]["totalRows"] = int(match.group(1))
        return

    if event_type == "browser":
        browser = {k: v for k, v in event.items() if k != "type"}
        snapshot["browser"] = {**snapshot.get("browser", {}), **browser}
        metrics = snapshot.setdefault("metrics", {})
        total = event.get("total")
        if isinstance(total, int) and total > 0:
            metrics["totalRows"] = total
        if event.get("event") in {"contacts", "no_pdf"}:
            processed = int(metrics.get("processedRows") or 0) + 1
            metrics["processedRows"] = processed
            status = str(event.get("status") or "")
            if event.get("event") == "no_pdf" or status == "not_found":
                metrics["notFoundRows"] = int(metrics.get("notFoundRows") or 0) + 1
            elif status == "found":
                metrics["foundRows"] = int(metrics.get("foundRows") or 0) + 1
            else:
                metrics["errorRows"] = int(metrics.get("errorRows") or 0) + 1
        return

    if event_type == "pipeline_stats":
        metrics = snapshot.setdefault("metrics", {})
        metrics["totalRows"] = int(event.get("total") or metrics.get("totalRows") or 0)
        metrics["foundRows"] = int(event.get("found") or 0)
        metrics["notFoundRows"] = int(event.get("not_found") or 0)
        metrics["errorRows"] = int(event.get("errors") or 0)
        metrics["processedRows"] = metrics["foundRows"] + metrics["notFoundRows"] + metrics["errorRows"]
        snapshot["pipeline"] = event
        return

    if event_type in {"complete", "error"}:
        snapshot["lastEvent"] = event
        if event_type == "complete":
            result = event.get("result") if isinstance(event.get("result"), dict) else {}
            summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
            metrics = snapshot.setdefault("metrics", {})
            metrics["totalRows"] = int(summary.get("total") or metrics.get("totalRows") or 0)
            metrics["processedRows"] = int(summary.get("processed") or metrics.get("processedRows") or 0)
            metrics["foundRows"] = int(summary.get("found") or metrics.get("foundRows") or 0)
            metrics["notFoundRows"] = int(summary.get("not_found") or metrics.get("notFoundRows") or 0)
            metrics["errorRows"] = int(summary.get("errors") or metrics.get("errorRows") or 0)
        return

# Directories
PROJECT_DIR = Path(__file__).parent
STATIC_DIR = PROJECT_DIR / "static"
UPLOADS_DIR = PROJECT_DIR / "uploads"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
PCT_OUTPUTS_DIR = OUTPUTS_DIR / "pct-work-sheets"
LOGS_DIR = PROJECT_DIR / "logs"
MENTESO_DIR = PROJECT_DIR / ".menteso"
WIPO_GAZETTES_CACHE = STATIC_DIR / "wipo_gazettes_cache.json"
DEPLOYMENT_LOG_FILE = LOGS_DIR / "deployments.jsonl"
SEO_INDEXING_STATE_FILE = PROJECT_DIR / "agents" / "patentzoom_seo_agent" / "state" / "indexing-status.json"
SEO_SCHEDULER_STATE_FILE = PROJECT_DIR / "agents" / "patentzoom_seo_agent" / "state" / "scheduler-state.json"
SEO_BROWSER_PROFILE_DIR = PROJECT_DIR / "agents" / "patentzoom_seo_agent" / "runtime" / "browser" / "google-search-console"
ENV_FILE = PROJECT_DIR / ".env"
USERS_FILE = MENTESO_DIR / "users.json"
SESSION_SECRET_FILE = MENTESO_DIR / "session.secret"
AUTH_COOKIE_NAME = "menteso_os_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
DEFAULT_ADMIN_USERNAME = os.getenv("MENTESO_OS_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("MENTESO_OS_ADMIN_PASSWORD", "")
AUTH_EXEMPT_PATHS = {
    "/login",
    "/api/login",
    "/favicon.ico",
    "/api/accountant/gmail-push",
    # Customer payment links are protected by short-lived HMAC tokens, while
    # Stripe protects its callback with the webhook signing secret. Requiring
    # an OS dashboard login here makes emailed payment links unusable.
    "/pay/invoices",
    "/pay/success",
    "/api/pay/invoices/checkout",
    "/api/pay/stripe/webhook",
}
ACCOUNTANT_PUSH_AUDIENCE = os.getenv(
    "ACCOUNTANT_PUSH_AUDIENCE", "https://os.menteso.com/api/accountant/gmail-push"
)
ACCOUNTANT_PUSH_SA_EMAIL = os.getenv(
    "ACCOUNTANT_PUSH_SA_EMAIL",
    "invoice-agent-push@invoicereqagent.iam.gserviceaccount.com",
)
ACCOUNTANT_TRIGGER_FILE = Path(os.getenv(
    "ACCOUNTANT_TRIGGER_FILE", "/app/accountant-status/gmail-push.trigger"
))
UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)
PCT_OUTPUTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
MENTESO_DIR.mkdir(exist_ok=True)

# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _json_response(status_code: int, payload: dict):
    return JSONResponse(payload, status_code=status_code)


def _password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"pbkdf2_sha256$200000${salt}${base64.b64encode(digest).decode('ascii')}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, rounds_text, salt, expected = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(rounds_text))
        actual = base64.b64encode(digest).decode("ascii")
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _read_json_file(path: Path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    return fallback


def _write_json_file(path: Path, payload):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _ensure_auth_files():
    if not SESSION_SECRET_FILE.exists():
        SESSION_SECRET_FILE.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    payload = _read_json_file(USERS_FILE, {})
    users = payload.get("users") if isinstance(payload, dict) else None
    if not isinstance(users, list) or not users:
        _write_json_file(USERS_FILE, {
            "version": 1,
            "roles": {
                "admin": ["*"],
                "operator": ["read", "run_agents"],
                "viewer": ["read"],
            },
            "users": [
                {
                    "username": DEFAULT_ADMIN_USERNAME,
                    "display_name": "Menteso Admin",
                    "role": "admin",
                    "active": True,
                    "password_hash": _password_hash(DEFAULT_ADMIN_PASSWORD),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        })


def _load_users_payload():
    _ensure_auth_files()
    payload = _read_json_file(USERS_FILE, {})
    if not isinstance(payload, dict):
        return {"users": [], "roles": {}}
    return payload


def _session_secret() -> bytes:
    _ensure_auth_files()
    return SESSION_SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")


def _sign_session(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    signature = hmac.new(_session_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _decode_session(cookie_value: str | None):
    if not cookie_value or "." not in cookie_value:
        return None
    encoded, signature = cookie_value.rsplit(".", 1)
    expected = hmac.new(_session_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padded = encoded + ("=" * (-len(encoded) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    return payload


def _find_user(username: str):
    for user in _load_users_payload().get("users", []):
        if str(user.get("username", "")).lower() == username.lower():
            return user
    return None


def _public_user(user: dict):
    return {
        "username": user.get("username"),
        "display_name": user.get("display_name") or user.get("username"),
        "role": user.get("role") or "viewer",
        "active": bool(user.get("active", True)),
    }


def _request_user(request: Request):
    session = _decode_session(request.cookies.get(AUTH_COOKIE_NAME))
    if not session:
        return None
    user = _find_user(str(session.get("sub") or ""))
    if not user or not user.get("active", True):
        return None
    return user


def _is_auth_exempt(path: str) -> bool:
    return path in AUTH_EXEMPT_PATHS or path.startswith("/static/")


@app.middleware("http")
async def require_app_login(request: Request, call_next):
    if _is_auth_exempt(request.url.path):
        return await call_next(request)
    user = _request_user(request)
    if user:
        request.state.user = user
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return _json_response(401, {"error": "login_required"})
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    html_path = STATIC_DIR / "login.html"
    with open(html_path, encoding="utf-8") as f:
        return f.read()


@app.post("/api/login")
async def api_login(request: Request):
    try:
        payload = await request.json()
    except Exception:
        form = await request.form()
        payload = dict(form)
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    user = _find_user(username)
    if not user or not user.get("active", True) or not _verify_password(password, str(user.get("password_hash") or "")):
        return _json_response(401, {"ok": False, "error": "invalid_credentials"})
    now = int(time.time())
    session = _sign_session({
        "sub": user.get("username"),
        "role": user.get("role") or "viewer",
        "iat": now,
        "exp": now + SESSION_TTL_SECONDS,
    })
    response = JSONResponse({"ok": True, "user": _public_user(user)})
    response.set_cookie(
        AUTH_COOKIE_NAME,
        session,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/logout")
async def api_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return response


@app.get("/api/auth/me")
async def auth_me(request: Request):
    return {"ok": True, "user": _public_user(request.state.user)}


@app.on_event("startup")
async def startup_event():
    try:
        db_storage.ensure_schema()
    except Exception as exc:
        print(f"Database schema initialization skipped: {exc}", file=sys.stderr)
    try:
        threading.Thread(target=_bootstrap_database_snapshots, daemon=True, name="db-snapshot-bootstrap").start()
    except Exception as exc:
        print(f"Database snapshot bootstrap skipped: {exc}", file=sys.stderr)
    try:
        if not _is_truthy(os.getenv("MENTESO_DISABLE_EMBEDDED_SEO_SCHEDULER", "false")):
            _ensure_local_seo_scheduler()
            print("SEO scheduler started.")
    except Exception as exc:
        print(f"SEO scheduler startup skipped: {exc}", file=sys.stderr)


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
    # Container deployments provide runtime configuration through process
    # environment variables rather than an /app/.env file.
    data.update(os.environ)
    return data


def _resolve_seo_workspace_id(workspace_id: str | None):
    default_workspace = "patent-drawing-experts"
    key = str(workspace_id or default_workspace).strip().lower() or default_workspace
    return key if key in SEO_WORKSPACE_PROPERTY_KEYS else default_workspace


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


def _public_base_url():
    env = _load_env_map()
    for key in ["PUBLIC_BASE_URL", "APP_BASE_URL", "CLOUDFLARE_TUNNEL_URL", "NEXT_PUBLIC_SEO_API_BASE_URL"]:
        value = str(env.get(key) or os.getenv(key) or "").strip().rstrip("/")
        if value.startswith("https://") or value.startswith("http://"):
            return value
    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    return f"http://{host}:{os.getenv('DASHBOARD_PORT', '8000')}"


def _google_oauth_redirect_uri():
    env = _load_env_map()
    configured = str(env.get("GOOGLE_OAUTH_REDIRECT_URI") or os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
    if configured:
        return configured
    return f"{_public_base_url()}/api/google/search-console/callback"


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
    if (
        name == "patentzoom_seo_agent"
        and os.getenv("MENTESO_EXECUTION_TARGET", "local").lower() == "local"
    ):
        return {
            "ok": False,
            "response": JSONResponse(
                {"error": "SEO Agent is hosted on AWS and cannot execute on the local server."},
                status_code=409,
            ),
        }

    payload = dict(input_data or {})
    run_id = str(payload.get("run_id") or f"{name}-{int(time.time())}-{secrets.token_hex(4)}")
    payload["run_id"] = run_id

    status = _get_run_status(name)
    if status["status"] != "idle":
        msg = "Agent is stopping, please wait" if status["status"] == "stopping" else "Agent is already running"
        return {"ok": False, "response": JSONResponse({"error": msg, "status": status["status"]}, status_code=409)}

    stop_event = threading.Event()
    # Live fast-mode level shared between the HTTP layer and the running
    # agent. The slider in the dashboard POSTs to /fast-level which mutates
    # control["fast_level"] in place; the agent reads it via the callable
    # we inject below at every chunk boundary, so dragging the slider mid-
    # run actually changes future chunks.
    initial_level = payload.get("fast_level")
    try:
        initial_level = int(initial_level) if initial_level is not None else None
    except (TypeError, ValueError):
        initial_level = None
    if initial_level is None:
        # leave to agent's resolve_fast_level() defaults (env / 1)
        initial_level = 0
    control = {
        "stop_event": stop_event,
        "thread": None,
        "interruptors": [],
        "fast_level": initial_level,
        "emit": emit,
    }
    RUN_LIVE_STATUS[name] = {
        "run_id": run_id,
        "input": {k: v for k, v in payload.items() if k in {"file_path", "mode", "gazette", "fast_level"}},
        "logs": [],
        "metrics": {
            "totalRows": 0,
            "processedRows": 0,
            "foundRows": 0,
            "notFoundRows": 0,
            "errorRows": 0,
        },
        "browser": {},
        "updatedAt": _now_iso(),
    }
    payload["stop_requested"] = stop_event.is_set
    payload["get_live_fast_level"] = (
        lambda: control.get("fast_level") if control.get("fast_level") else None
    )

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
            _persist_agent_completion(name, result if isinstance(result, dict) else {}, payload, run_id=run_id)
            if emit:
                emit(completion)
        except Exception as e:
            completion = {"type": "error", "message": str(e), "traceback": traceback.format_exc()}
            _persist_agent_completion(
                name,
                {"status": "failure", "error": str(e), "traceback": completion["traceback"]},
                payload,
                run_id=run_id,
            )
            print(completion["traceback"], file=sys.stderr)
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
    previous_status = str(state.get("last_auto_result_status") or "").strip().lower()
    if str(state.get("last_auto_attempt_date") or "").strip() == today_iso and previous_status in {"running", "success", "failure"}:
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
    today_iso = _ist_now().strftime("%Y-%m-%d")
    for workspace_id in SEO_WORKSPACE_AUTO_PUBLISH_KEYS:
        state = _load_seo_scheduler_state(workspace_id)
        if (
            str(state.get("last_auto_attempt_date") or "").strip() == today_iso
            and str(state.get("last_auto_result_status") or "").strip().lower() == "failure"
            and "quota" in str(state.get("last_auto_error") or "").strip().lower()
        ):
            return

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


def _run_local_command(args, timeout=15):
    try:
        completed = subprocess.run(
            args,
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return {
            "ok": completed.returncode == 0,
            "code": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
        }
    except Exception as exc:
        return {"ok": False, "code": None, "stdout": "", "stderr": str(exc)}


def _read_jsonl_tail(path: Path, limit=8):
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []

    entries = []
    for line in lines[-max(limit * 3, limit):]:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                entries.append(item)
        except Exception:
            continue
    return entries[-limit:]


def _pct_progress_candidates():
    candidates = []
    for directory in [PCT_OUTPUTS_DIR, OUTPUTS_DIR]:
        if directory.exists():
            candidates.extend(directory.glob("pct_progress_*.jsonl"))
    return sorted(set(candidates), reverse=True)


def _resolve_output_download_path(filename: str):
    safe_name = Path(str(filename or "")).name
    if not safe_name:
        return None
    for directory in [PCT_OUTPUTS_DIR, OUTPUTS_DIR]:
        candidate = (directory / safe_name).resolve()
        directory_resolved = directory.resolve()
        if directory_resolved in candidate.parents and candidate.exists():
            return candidate
    return None


def _mask_host(host: str):
    host = str(host or "").strip()
    if not host:
        return ""
    if len(host) <= 4:
        return host[:1] + "***"
    return host[:2] + "***" + host[-2:]


def _database_admin_status():
    db_storage.ensure_schema()
    store_path = getattr(db_storage, "STORE_PATH", PROJECT_DIR / "shared" / "agent_data.json")
    exists = Path(store_path).exists()
    size = Path(store_path).stat().st_size if exists else 0
    return {
        "configured": True,
        "urls": {},
        "driver": "json_file",
        "usedByAppCode": True,
        "connected": True,
        "connectionCheck": {
            "attempted": True,
            "ok": True,
            "message": "Agent and dashboard data is stored in a local JSON file.",
        },
        "store": {
            "path": str(store_path),
            "exists": exists,
            "sizeBytes": size,
        },
        "note": "Postgres is disabled. Menteso_OS now stores agent snapshots, runs, events, artifacts, and dashboard state in the local JSON data file.",
    }


def _pm2_admin_status():
    result = _run_local_command(["cmd", "/c", "pm2", "jlist"], timeout=20)
    processes = []
    if result.get("ok") and result.get("stdout"):
        try:
            payload = json.loads(result["stdout"])
            for item in payload if isinstance(payload, list) else []:
                env = item.get("pm2_env", {}) if isinstance(item, dict) else {}
                processes.append({
                    "name": item.get("name", ""),
                    "pid": item.get("pid") or env.get("pm_pid"),
                    "status": env.get("status", "unknown"),
                    "restarts": env.get("restart_time", 0),
                    "uptimeMs": int(time.time() * 1000) - int(env.get("pm_uptime") or 0) if env.get("pm_uptime") else None,
                    "script": env.get("pm_exec_path", ""),
                    "args": " ".join(env.get("args") or []),
                    "watching": bool(env.get("watch")),
                })
        except Exception:
            pass
    return {
        "ok": result.get("ok", False),
        "processes": processes,
        "error": result.get("stderr", "") if not result.get("ok") else "",
    }


def _git_admin_status():
    branch = _run_local_command(["git", "branch", "--show-current"], timeout=10)
    head = _run_local_command(["git", "rev-parse", "--short", "HEAD"], timeout=10)
    commit = _run_local_command(["git", "log", "-1", "--pretty=format:%h|%an|%ar|%s"], timeout=10)
    remote = _run_local_command(["git", "remote", "get-url", "origin"], timeout=10)
    status = _run_local_command(["git", "status", "--short"], timeout=10)
    return {
        "branch": branch.get("stdout", ""),
        "head": head.get("stdout", ""),
        "latestCommit": commit.get("stdout", ""),
        "remote": remote.get("stdout", ""),
        "dirty": bool(status.get("stdout", "")),
        "changes": status.get("stdout", "").splitlines()[:20],
    }


def _workflow_admin_status():
    workflow_path = PROJECT_DIR / ".github" / "workflows" / "deploy-main.yml"
    script_path = PROJECT_DIR / "scripts" / "deploy.ps1"
    return {
        "workflowPresent": workflow_path.exists(),
        "deployScriptPresent": script_path.exists(),
        "trigger": "push to main and manual workflow_dispatch",
        "serverAction": "git pull origin main, install dependencies, build/test, reload PM2, health check",
        "requiredSecrets": ["DEPLOY_HOST", "DEPLOY_USER", "DEPLOY_SSH_KEY", "DEPLOY_PORT"],
    }


def _callback_admin_status():
    env = _load_env_map()
    base = _public_base_url()
    return {
        "publicBaseUrl": base,
        "googleSearchConsole": str(env.get("GOOGLE_OAUTH_REDIRECT_URI") or "").strip() or f"{base}/api/google/search-console/callback",
        "meta": str(env.get("META_OAUTH_REDIRECT_URI") or "").strip() or f"{base}/api/meta/callback",
        "linkedin": str(env.get("LINKEDIN_OAUTH_REDIRECT_URI") or "").strip() or f"{base}/api/linkedin/callback",
    }


def _agent_last_activity(agent_name: str):
    memory = load_memory(agent_name)
    learnings = memory.get("learnings", []) if isinstance(memory, dict) else []
    last_learning = learnings[-1] if learnings else None
    artifact = {}
    if agent_name == "pct_agent":
        candidates = _pct_progress_candidates()
        if candidates:
            artifact = {
                "file": candidates[0].name,
                "updatedAt": datetime.fromtimestamp(candidates[0].stat().st_mtime, timezone.utc).isoformat(),
            }
    elif agent_name == "patentzoom_seo_agent":
        generated_posts = _seo_workspace_state_paths("patentzoom")["generated_posts"]
        if generated_posts.exists():
            artifact = {
                "file": generated_posts.name,
                "updatedAt": datetime.fromtimestamp(generated_posts.stat().st_mtime, timezone.utc).isoformat(),
            }

    return {
        "runStatus": _get_run_status(agent_name).get("status", "idle"),
        "lastLearning": last_learning,
        "lastArtifact": artifact,
        "stats": memory.get("stats", {}) if isinstance(memory, dict) else {},
        "learningCount": len(learnings),
    }


def _result_workspace_id(agent_name: str, result: dict | None, payload: dict | None = None):
    result = result if isinstance(result, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    if agent_name == "patentzoom_seo_agent":
        return _resolve_seo_workspace_id(
            result.get("workspaceId")
            or result.get("workspace_id")
            or payload.get("workspace_id")
            or payload.get("workspaceId")
        )
    return str(result.get("workspaceId") or payload.get("workspace_id") or payload.get("workspaceId") or "").strip()


def _persist_agent_completion(agent_name: str, result: dict | None, payload: dict | None = None, run_id: str = ""):
    if not isinstance(result, dict):
        return
    workspace_id = _result_workspace_id(agent_name, result, payload)
    memory_key = agent_name
    if agent_name == "patentzoom_seo_agent" and workspace_id and workspace_id != "patentzoom":
        memory_key = f"{agent_name}/workspaces/{workspace_id}"
    memory = load_memory(memory_key)
    status = str(result.get("status") or result.get("postStatus") or "unknown")
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    execution_time = result.get("executionTime", result.get("execution_time"))
    try:
        execution_time = float(execution_time) if execution_time is not None else None
    except (TypeError, ValueError):
        execution_time = None

    try:
        safe_dashboard_result = _database_safe_agent_payload(agent_name, result)
        safe_run_result = _database_safe_agent_payload(agent_name, result)
        db_storage.upsert_agent_snapshot(
            agent_name,
            workspace_id=workspace_id,
            agent_name=agent_name,
            memory=memory,
            stats=memory.get("stats", {}) if isinstance(memory, dict) else {},
            dashboard={
                "lastResult": safe_dashboard_result,
                "runStatus": _get_run_status(agent_name).get("status", "idle"),
                "updatedAt": _now_iso(),
            },
        )
        db_storage.insert_agent_run(
            agent_name,
            workspace_id=workspace_id,
            run_id=run_id,
            task="daily_seo_blog" if agent_name == "patentzoom_seo_agent" else "process_excel",
            status=status,
            result=safe_run_result,
            summary=summary,
            execution_time=execution_time,
        )
        if result.get("wordpressUrl"):
            db_storage.insert_artifact(
                agent_name,
                workspace_id=workspace_id,
                run_id=run_id,
                artifact_type="wordpress_post",
                name=str(result.get("title") or result.get("topic") or result.get("primaryKeyword") or ""),
                url=str(result.get("wordpressUrl") or ""),
                payload=result,
            )
        if result.get("output_file"):
            output_path = str(result.get("output_file") or "")
            db_storage.insert_artifact(
                agent_name,
                workspace_id=workspace_id,
                run_id=run_id,
                artifact_type="output_file",
                name=Path(output_path).name,
                path=output_path,
                payload={"summary": summary},
            )
        if agent_name == "pct_agent":
            pct_summary = summary if isinstance(summary, dict) else {}
            subagents = {
                "Scraper": {
                    "processed": pct_summary.get("processed", 0),
                    "found": pct_summary.get("found", 0),
                    "not_found": pct_summary.get("not_found", 0),
                },
                "PDF Extractor": {
                    "processed": pct_summary.get("processed", 0),
                    "errors": pct_summary.get("errors", 0),
                },
                "CAPTCHA Solver": {
                    "status": "available",
                    "captchaEvents": result.get("captcha_events", 0),
                },
            }
            for subagent_name, subagent_stats in subagents.items():
                db_storage.upsert_subagent_snapshot(
                    agent_name,
                    subagent_name,
                    workspace_id=workspace_id,
                    status="active",
                    stats=subagent_stats,
                    payload=subagent_stats,
                )
            if result.get("output_file") and str(result.get("status") or "").lower() in {"success", "stopped"}:
                try:
                    email_result = send_pct_completion_email(result)
                    if email_result.get("sent"):
                        db_storage.insert_artifact(
                            agent_name,
                            workspace_id=workspace_id,
                            run_id=run_id,
                            artifact_type="email_notification",
                            name="PCT completion email",
                            payload={
                                "to": email_result.get("to", []),
                                "attached": email_result.get("attached", False),
                                "skippedAttachmentReason": email_result.get("skippedAttachmentReason", ""),
                            },
                        )
                except Exception as email_exc:
                    print(f"PCT completion email failed: {email_exc}", file=sys.stderr)
    except Exception as exc:
        print(f"Database run persistence skipped for {agent_name}: {exc}", file=sys.stderr)


def _database_safe_agent_payload(agent_name: str, payload):
    """Keep PCT sheet/contact output local-only.

    PCT results can contain every processed row plus extracted contact data.
    The database is for dashboard metadata, run status, counts, and local
    artifact pointers only.
    """
    if not isinstance(payload, dict):
        return payload
    if agent_name != "pct_agent":
        return payload

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    execution_time = payload.get("execution_time", payload.get("executionTime", 0)) or 0
    try:
        execution_seconds = float(execution_time)
    except (TypeError, ValueError):
        execution_seconds = 0.0
    processed = summary.get("processed", 0) or 0
    try:
        processed_number = float(processed)
    except (TypeError, ValueError):
        processed_number = 0.0
    rows_per_minute = round((processed_number / execution_seconds) * 60, 2) if execution_seconds > 0 else 0
    safe = {
        "status": payload.get("status", ""),
        "error": payload.get("error", ""),
        "summary": {
            "total": summary.get("total", 0),
            "processed": summary.get("processed", 0),
            "found": summary.get("found", 0),
            "not_found": summary.get("not_found", 0),
            "errors": summary.get("errors", 0),
            "skipped": summary.get("skipped", 0),
        },
        "output_file": payload.get("output_file", ""),
        "input_file": payload.get("input_file", ""),
        "input_file_name": payload.get("input_file_name", ""),
        "mode": payload.get("mode", ""),
        "gazette": payload.get("gazette", ""),
        "week_or_sheet": payload.get("gazette") or payload.get("input_file_name") or "",
        "timestamp": payload.get("timestamp", ""),
        "execution_time": execution_time,
        "benchmark": {
            "execution_seconds": round(execution_seconds, 2),
            "rows_per_minute": rows_per_minute,
            "found_rate": round((float(summary.get("found", 0) or 0) / processed_number), 4) if processed_number else 0,
            "not_found_rate": round((float(summary.get("not_found", 0) or 0) / processed_number), 4) if processed_number else 0,
        },
        "attempts": payload.get("attempts", 1),
        "tests": payload.get("tests", {}),
    }
    if safe["output_file"]:
        safe["output_file_name"] = Path(str(safe["output_file"])).name
    return safe


def _database_safe_agent_event(agent_name: str, event):
    if agent_name != "pct_agent":
        return event
    if not isinstance(event, dict):
        message = str(event)
        if message.startswith("[Row ") or "FOUND:" in message:
            return None
        return {"message": message}

    event_type = str(event.get("type") or "step")
    message = str(event.get("message") or "")
    if event_type in {"browser", "pipeline_stats"} or event.get("row") or event.get("patent_id"):
        return None
    if message.startswith("[Row ") or "FOUND:" in message:
        return None

    safe = {
        "type": event_type,
        "message": message,
    }
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    allowed_data = {}
    for key in ["stage", "status", "row", "total", "event", "url", "patent_id", "country"]:
        if key in data:
            allowed_data[key] = data[key]
    for key in ["row", "total", "event", "url", "patent_id", "country"]:
        if key in event:
            allowed_data[key] = event[key]
    if allowed_data:
        safe["data"] = allowed_data
    if event.get("timestamp"):
        safe["timestamp"] = event.get("timestamp")
    return safe


def _bootstrap_database_snapshots():
    if not db_storage.db_enabled():
        return
    for agent_config in discover_agents():
        module_name = agent_config.get("module_name", "")
        if not module_name:
            continue
        memory = load_memory(module_name)
        db_storage.upsert_agent_snapshot(
            module_name,
            agent_name=agent_config.get("name") or module_name,
            dashboard={
                "agent": agent_config,
                "activity": _agent_last_activity(module_name),
                "source": "startup_bootstrap",
                "updatedAt": _now_iso(),
            },
            memory=memory,
            stats=memory.get("stats", {}) if isinstance(memory, dict) else {},
        )
        for subagent_name in agent_config.get("sub_agents") or []:
            db_storage.upsert_subagent_snapshot(
                module_name,
                subagent_name,
                status="active" if agent_config.get("status") == "active" else str(agent_config.get("status") or ""),
                stats={},
                payload={"source": "agent_config"},
            )


def _admin_status_payload():
    agents = []
    for agent_config in discover_agents():
        module_name = agent_config.get("module_name", "")
        agents.append({
            **agent_config,
            "activity": _agent_last_activity(module_name),
        })
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "server": {
            "cwd": str(PROJECT_DIR),
            "host": os.getenv("DASHBOARD_HOST", "0.0.0.0"),
            "port": os.getenv("DASHBOARD_PORT", "8000"),
        },
        "agents": agents,
        "pm2": _pm2_admin_status(),
        "git": _git_admin_status(),
        "deployment": {
            **_workflow_admin_status(),
            "history": _read_jsonl_tail(DEPLOYMENT_LOG_FILE, limit=10),
        },
        "callbacks": _callback_admin_status(),
        "database": _database_admin_status(),
    }


# ---------------------------------------------------------------------------
# Root — serve dashboard HTML
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = STATIC_DIR / "index.html"
    with open(html_path, encoding="utf-8") as f:
        return f.read()


@app.get("/admin-dashbaord", response_class=HTMLResponse)
async def admin_dashbaord():
    html_path = STATIC_DIR / "admin-dashboard.html"
    with open(html_path, encoding="utf-8") as f:
        return f.read()


@app.get("/admin-dashboard", response_class=HTMLResponse)
async def admin_dashboard_alias():
    return await admin_dashbaord()


@app.get("/api/admin/status")
async def admin_status():
    return _admin_status_payload()


@app.post("/api/accountant/gmail-push")
async def accountant_gmail_push(request: Request):
    """Authenticated Pub/Sub webhook that wakes the AWS AccountantAgent."""
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        print("Accountant push rejected: missing bearer identity", file=sys.stderr)
        return _json_response(403, {"error": "missing_push_identity"})
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        claims = id_token.verify_oauth2_token(
            authorization.split(" ", 1)[1].strip(),
            google_requests.Request(),
            audience=None,
            clock_skew_in_seconds=10,
        )
    except Exception as exc:
        print(f"Accountant push rejected: invalid OIDC token ({type(exc).__name__}: {exc})", file=sys.stderr)
        return _json_response(403, {"error": "invalid_push_identity"})
    if str(claims.get("aud") or "").strip() != ACCOUNTANT_PUSH_AUDIENCE:
        print("Accountant push rejected: audience mismatch", file=sys.stderr)
        return _json_response(403, {"error": "unexpected_push_audience"})
    if claims.get("email") != ACCOUNTANT_PUSH_SA_EMAIL:
        print(
            f"Accountant push rejected: identity {claims.get('email')!r} does not match expected service account",
            file=sys.stderr,
        )
        return _json_response(403, {"error": "unexpected_push_identity"})

    try:
        envelope = await request.json()
        encoded = (envelope.get("message") or {}).get("data") or ""
        notification = json.loads(base64.b64decode(encoded).decode("utf-8"))
    except Exception:
        return _json_response(400, {"error": "invalid_pubsub_message"})
    if str(notification.get("emailAddress", "")).lower() != "invoicerequest@menteso.com":
        return _json_response(202, {"status": "ignored_mailbox"})

    try:
        ACCOUNTANT_TRIGGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACCOUNTANT_TRIGGER_FILE.write_text(
            datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"Accountant trigger write failed: {exc}", file=sys.stderr)
        return _json_response(503, {"error": "agent_trigger_unavailable"})
    return _json_response(200, {"status": "accepted"})


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


def _refresh_seo_dashboard_cache(workspace_id: str):
    try:
        payload = get_seo_dashboard_data(workspace_id)
        with SEO_DASHBOARD_CACHE_LOCK:
            SEO_DASHBOARD_CACHE[workspace_id] = {
                "loaded_at": time.time(),
                "payload": payload,
            }
        return payload
    except Exception as exc:
        print(f"SEO dashboard refresh failed for {workspace_id}: {exc}", file=sys.stderr)
        return None


def _prewarm_seo_dashboard_cache():
    for workspace_id in SEO_WORKSPACE_PROPERTY_KEYS:
        _refresh_seo_dashboard_cache(workspace_id)


@app.on_event("startup")
async def prewarm_seo_dashboard_cache():
    threading.Thread(
        target=_prewarm_seo_dashboard_cache,
        daemon=True,
        name="seo-dashboard-prewarm",
    ).start()


@app.get("/api/agents/{name}/dashboard-data")
async def agent_dashboard_data(name: str, workspace_id: str = "patent-drawing-experts"):
    if name == "patentzoom_seo_agent":
        workspace_id = _resolve_seo_workspace_id(workspace_id)
        with SEO_DASHBOARD_CACHE_LOCK:
            cached = SEO_DASHBOARD_CACHE.get(workspace_id)
        if cached:
            if time.time() - cached["loaded_at"] > SEO_DASHBOARD_CACHE_TTL_SECONDS:
                threading.Thread(
                    target=_refresh_seo_dashboard_cache,
                    args=(workspace_id,),
                    daemon=True,
                ).start()
            return cached["payload"]
        payload = await asyncio.to_thread(_refresh_seo_dashboard_cache, workspace_id)
        if payload is None:
            return JSONResponse({"error": "SEO dashboard data is temporarily unavailable"}, status_code=503)
        return payload
    if name == "accountant_agent":
        return get_accountant_dashboard_data()
    return JSONResponse({"error": "Dashboard data is not available for this agent"}, status_code=404)


@app.post("/api/accountant/reminders/control")
async def accountant_reminder_control(payload: dict = Body(...)):
    """Pause or resume the reminder workflow or one customer from the admin UI."""
    try:
        state = json.loads(OVERDUE_REMINDER_STATUS_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return JSONResponse({"error": "Reminder state is unavailable"}, status_code=503)
    action = str(payload.get("action") or "").lower()
    customer_id = str(payload.get("customer_id") or "")
    if action not in {"pause", "resume"}:
        return JSONResponse({"error": "Action must be pause or resume"}, status_code=400)
    paused = action == "pause"
    if customer_id:
        row = state.setdefault("customers", {}).get(customer_id)
        if row is None:
            return JSONResponse({"error": "Customer was not found"}, status_code=404)
        row["paused"] = paused
        row["status"] = "paused" if paused else ("test_ready" if state.get("mode") == "test" else "ready")
        row["updated_at"] = datetime.now(timezone.utc).isoformat()
    else:
        state["paused"] = paused
    temporary = OVERDUE_REMINDER_STATUS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(OVERDUE_REMINDER_STATUS_FILE)
    return {"ok": True, "paused": paused, "customer_id": customer_id or None}


@app.get("/api/google/search-console/status")
async def google_search_console_status(workspace_id: str = "patentzoom"):
    return _google_search_console_status(workspace_id)


@app.get("/pay/invoices", response_class=HTMLResponse)
async def multi_invoice_portal(token: str = ""):
    try:
        _state, customer = _payment_customer(token)
    except Exception as exc:
        return HTMLResponse(f"<h2>Payment link unavailable</h2><p>{str(exc)}</p>", status_code=400)
    invoice_data = customer.get("invoices", [])
    rows = "".join(
        f'''<label class="invoice"><input type="checkbox" value="{i['id']}" checked>
        <span><b>Invoice {i['number']}</b><small>Due {i['due_date']} · {i['amount_due']} {i['currency']}</small></span>
        <a href="{i['preview_url']}" target="_blank" rel="noopener">Preview</a></label>'''
        for i in invoice_data
    )
    amounts = json.dumps([i.get("amount_due") for i in invoice_data])
    safe_token = token.replace('"', "&quot;")
    currency = customer.get("currency", "USD")
    return HTMLResponse(f'''<!doctype html><html><head><meta name="viewport" content="width=device-width"><title>Outstanding invoices</title>
    <style>body{{font:16px Arial;background:#f5f7fb;color:#172033;margin:0}}main{{max-width:720px;margin:40px auto;background:white;padding:28px;border-radius:12px;box-shadow:0 8px 30px #0001}}.invoice{{display:flex;gap:14px;align-items:center;border:1px solid #dbe2ee;padding:16px;margin:12px 0;border-radius:9px}}.invoice span{{flex:1}}small{{display:block;color:#64748b;margin-top:5px}}button{{background:#1d4ed8;color:white;border:0;padding:13px 22px;border-radius:7px;font-weight:bold;font-size:16px}}#total{{font-size:20px;font-weight:bold;margin:22px 0}}a{{color:#1d4ed8}}</style></head>
    <body><main><h1>Review outstanding invoices</h1><p>{customer.get('customer','')}</p>{rows}<div id="total"></div>
    <button id="pay">Pay selected invoices securely</button><p><small>Stripe securely hosts card processing. Menteso does not receive your card details.</small></p></main>
    <script>const token="{safe_token}",amounts={amounts},boxes=[...document.querySelectorAll('input')];function total(){{let n=0;boxes.forEach((b,i)=>{{if(b.checked)n+=Number(amounts[i].replace(',',''))}});document.querySelector('#total').textContent='Selected total: '+n.toFixed(2)+' {currency}'}}boxes.forEach(b=>b.onchange=total);total();document.querySelector('#pay').onclick=async()=>{{let ids=boxes.filter(b=>b.checked).map(b=>b.value);if(!ids.length)return alert('Select at least one invoice');let r=await fetch('/api/pay/invoices/checkout',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{token,invoice_ids:ids}})}});let d=await r.json();if(!r.ok)return alert(d.error||'Checkout unavailable');location.href=d.url}};</script></body></html>''')


@app.post("/api/pay/invoices/checkout")
async def create_multi_invoice_checkout(payload: dict = Body(...)):
    try:
        _state, customer = _payment_customer(str(payload.get("token") or ""))
        selected = {str(x) for x in payload.get("invoice_ids", [])}
        invoices = [i for i in customer.get("invoices", []) if i["id"] in selected]
        if not invoices:
            raise ValueError("Select at least one invoice")
        if len({i["currency"].lower() for i in invoices}) != 1:
            raise ValueError("Selected invoices must use the same currency")
        key = os.getenv("INVOICE_REMINDER_STRIPE_SECRET_KEY", "")
        if not key.startswith(("rk_live_", "sk_live_", "rk_test_", "sk_test_")):
            raise ValueError("Stripe Checkout is not configured")
        form = [("mode", "payment"), ("payment_method_types[]", "card"),
                ("customer_email", customer["email"]),
                ("success_url", "https://os.menteso.com/pay/success?session_id={CHECKOUT_SESSION_ID}"),
                ("cancel_url", f"https://os.menteso.com/pay/invoices?token={payload['token']}"),
                ("metadata[wave_customer_id]", customer["customer_id"]),
                ("metadata[wave_invoice_ids]", ",".join(i["id"] for i in invoices))]
        for n, invoice in enumerate(invoices):
            amount = int(round(float(str(invoice["amount_due"]).replace(",", "")) * 100))
            form += [(f"line_items[{n}][quantity]", "1"), (f"line_items[{n}][price_data][currency]", invoice["currency"].lower()),
                     (f"line_items[{n}][price_data][unit_amount]", str(amount)),
                     (f"line_items[{n}][price_data][product_data][name]", f"Invoice {invoice['number']}"),
                     (f"line_items[{n}][price_data][product_data][description]", f"Due {invoice['due_date']}")]
        response = requests.post("https://api.stripe.com/v1/checkout/sessions", auth=(key, ""), data=form, timeout=30,
                                 headers={"Idempotency-Key": hashlib.sha256(json.dumps(form).encode()).hexdigest()})
        response.raise_for_status()
        return {"url": response.json()["url"]}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/pay/success", response_class=HTMLResponse)
async def multi_invoice_success(session_id: str = ""):
    return HTMLResponse("<main style='font:16px Arial;max-width:650px;margin:60px auto'><h1>Thank you</h1><p>Your payment is being verified. A receipt will be sent after the selected invoices are reconciled.</p></main>")


@app.post("/api/pay/stripe/webhook")
async def stripe_invoice_webhook(request: Request):
    payload = await request.body()
    header = request.headers.get("stripe-signature", "")
    secret = os.getenv("INVOICE_REMINDER_STRIPE_WEBHOOK_SECRET", "")
    try:
        parts = [p.split("=", 1) for p in header.split(",") if "=" in p]
        stamp = int(next(v for k, v in parts if k == "t"))
        signatures = [v for k, v in parts if k == "v1"]
        if abs(int(time.time()) - stamp) > 300:
            raise ValueError("expired signature")
        expected = hmac.new(secret.encode(), str(stamp).encode() + b"." + payload, hashlib.sha256).hexdigest()
        if not secret or not any(hmac.compare_digest(expected, value) for value in signatures):
            raise ValueError("invalid signature")
        event = json.loads(payload)
        if event.get("type") != "checkout.session.completed":
            return {"received": True}
        session = event["data"]["object"]
        if session.get("payment_status") != "paid":
            return {"received": True}
        metadata = session.get("metadata") or {}
        customer_id = str(metadata.get("wave_customer_id") or "")
        invoice_ids = [x for x in str(metadata.get("wave_invoice_ids") or "").split(",") if x]
        state = json.loads(OVERDUE_REMINDER_STATUS_FILE.read_text(encoding="utf-8-sig"))
        events = state.setdefault("payment_events", {})
        if event["id"] not in events:
            row = state.setdefault("customers", {}).get(customer_id, {})
            selected = [i for i in row.get("invoices", []) if i.get("id") in invoice_ids]
            events[event["id"]] = {"status": "pending_reconciliation", "stripe_session_id": session["id"],
                                    "stripe_payment_intent": session.get("payment_intent"), "customer_id": customer_id,
                                    "invoices": selected, "created_at": datetime.now(timezone.utc).isoformat()}
            row["paused"] = True
            row["status"] = "payment_reconciliation"
            temporary = OVERDUE_REMINDER_STATUS_FILE.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
            temporary.replace(OVERDUE_REMINDER_STATUS_FILE)
        return {"received": True}
    except Exception:
        return JSONResponse({"error": "Invalid Stripe webhook"}, status_code=400)


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
    return_url = _public_base_url() + "/"
    if error:
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>Google connection failed</h2><p>{error}</p><p><a href='{return_url}' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>",
            status_code=400,
        )

    if not code or not state or state not in GOOGLE_OAUTH_STATES:
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>Google connection failed</h2><p>Missing or invalid OAuth callback state.</p><p><a href='{return_url}' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>",
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
            f"<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>Google connection failed</h2><pre style='white-space:pre-wrap'>{token_response.text}</pre><p><a href='{return_url}' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>",
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
        f"<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>Google Search Console connected</h2><p>You can close this tab and return to the Menteso SEO Posting Agent dashboard.</p><p><a href='{return_url}' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>"
    )


@app.get("/api/meta/callback", response_class=HTMLResponse)
async def meta_callback(request: Request):
    params = request.query_params
    challenge = params.get("hub.challenge")
    verify_token = params.get("hub.verify_token")
    expected_token = str(_load_env_map().get("META_WEBHOOK_VERIFY_TOKEN") or os.getenv("META_WEBHOOK_VERIFY_TOKEN") or "").strip()
    if challenge is not None:
        if expected_token and verify_token != expected_token:
            return JSONResponse({"error": "Invalid Meta webhook verify token"}, status_code=403)
        return HTMLResponse(str(challenge))

    return_url = _public_base_url() + "/"
    error = params.get("error") or params.get("error_message")
    code = params.get("code")
    if error:
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>Meta connection callback received</h2><p>{error}</p><p><a href='{return_url}' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>",
            status_code=400,
        )
    return HTMLResponse(
        f"<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>Meta callback endpoint is live</h2><p>{'Authorization code received.' if code else 'No authorization code was provided.'}</p><p>Token exchange is not implemented in this server yet; existing Meta publishing uses the configured access token env vars.</p><p><a href='{return_url}' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>"
    )


@app.get("/api/linkedin/callback", response_class=HTMLResponse)
async def linkedin_callback(request: Request):
    params = request.query_params
    return_url = _public_base_url() + "/"
    error = params.get("error") or params.get("error_description")
    code = params.get("code")
    if error:
        return HTMLResponse(
            f"<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>LinkedIn connection callback received</h2><p>{error}</p><p><a href='{return_url}' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>",
            status_code=400,
        )
    return HTMLResponse(
        f"<html><body style='font-family:sans-serif;padding:32px;background:#0b1220;color:#fff'><h2>LinkedIn callback endpoint is live</h2><p>{'Authorization code received.' if code else 'No authorization code was provided.'}</p><p>Token exchange is not implemented in this server yet; existing LinkedIn publishing uses the configured access token env vars.</p><p><a href='{return_url}' style='color:#8ab4ff'>Return to Menteso</a></p></body></html>"
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
    file_path = _resolve_output_download_path(filename)
    if not file_path:
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
    candidates = _pct_progress_candidates()
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


def _read_text_tail(path: Path, max_bytes: int = 2_000_000):
    try:
        if not path.exists():
            return ""
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            data = f.read()
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


@app.get("/api/agents/{name}/run-status")
async def agent_run_status(name: str):
    return _get_run_status(name)


@app.get("/api/agents/{name}/fast-level")
async def get_fast_level(name: str):
    """Return the currently-active fast-mode level for a run."""
    control = RUN_CONTROLS.get(name)
    level = control.get("fast_level") if control else 0
    return {"level": level or 0, "running": bool(control)}


@app.post("/api/agents/{name}/fast-level")
async def set_fast_level(name: str, payload: dict = Body(...)):
    """Update fast-mode level mid-run. Clamped to [1, 5]. The agent reads
    this value at chunk boundaries, so dragging the slider higher causes
    future chunks to spin up more workers.
    """
    raw = payload.get("level")
    try:
        level = int(raw)
    except (TypeError, ValueError):
        return JSONResponse({"error": "level must be an integer 1-5"}, status_code=400)
    level = max(1, min(5, level))
    control = RUN_CONTROLS.get(name)
    if not control:
        return JSONResponse(
            {"error": "Agent is not running — level applies only to active runs"},
            status_code=409,
        )
    control["fast_level"] = level
    emit = control.get("emit")
    if callable(emit):
        try:
            emit({"type": "fast_level_changed", "level": level})
        except Exception:
            pass
    return {"ok": True, "level": level}


def _start_agent_run(name: str, input_data: dict | None = None):
    msg_queue = queue.Queue()

    def emit(message):
        if message is None:
            msg_queue.put(None)
            return
        _update_live_status(name, message)
        try:
            safe_event = _database_safe_agent_event(name, message)
            if safe_event is None:
                raise ValueError("skip database event")
            workspace_id = _result_workspace_id(name, safe_event if isinstance(safe_event, dict) else {}, input_data or {})
            db_storage.insert_agent_event(
                name,
                workspace_id=workspace_id,
                run_id=str((input_data or {}).get("run_id") or ""),
                event_type=str(safe_event.get("type") or "step") if isinstance(safe_event, dict) else "step",
                message=str(safe_event.get("message") or safe_event.get("type") or "") if isinstance(safe_event, dict) else str(safe_event),
                payload=safe_event if isinstance(safe_event, dict) else {"message": safe_event},
            )
        except Exception:
            pass
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
    fast_level: int = None,
):
    input_data = {}
    if file_path:
        input_data["file_path"] = file_path
    if mode:
        input_data["mode"] = mode
    if gazette:
        input_data["gazette"] = gazette
    if fast_level is not None:
        input_data["fast_level"] = fast_level
    return _start_agent_run(name, input_data)


@app.post("/api/agents/{name}/run")
async def run_agent_sse_post(name: str, payload: dict = Body(default=None)):
    return _start_agent_run(name, payload)


@app.post("/api/agents/{name}/stop")
async def stop_agent_run(name: str):
    control = RUN_CONTROLS.get(name)
    if not control:
        return {"status": "idle", "note": "no active run"}

    thread = control.get("thread")
    # If the thread is already dead but the entry lingered (e.g. previous
    # crash before cleanup), treat Stop as a force-clear — no point asking
    # a dead thread to stop.
    if not thread or not thread.is_alive():
        RUN_CONTROLS.pop(name, None)
        return {"status": "cleared", "note": "stale entry removed"}

    if control.get("stop_event"):
        control["stop_event"].set()
    interrupt_sent = 0
    for interruptor in list(control.get("interruptors", [])):
        try:
            interruptor()
            interrupt_sent += 1
        except Exception:
            pass
    return {"status": "stop_requested", "interrupt_sent": interrupt_sent}


@app.post("/api/agents/{name}/force-clear")
async def force_clear_agent_run(name: str):
    """Hard-reset an agent's run state. Use when Stop alone doesn't bring
    the UI back to idle — typically because a previous worker thread
    crashed or got stuck. We signal stop + interruptors and then drop the
    entry so the UI can start a fresh run, even if the zombie thread
    refuses to die (it'll just be orphaned).
    """
    control = RUN_CONTROLS.get(name)
    if not control:
        return {"status": "idle", "note": "already cleared"}
    try:
        if control.get("stop_event"):
            control["stop_event"].set()
        for interruptor in list(control.get("interruptors", [])):
            try:
                interruptor()
            except Exception:
                pass
    finally:
        RUN_CONTROLS.pop(name, None)
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
