"""
PCT Sub-Agent: Browser Automation
Uses Playwright to navigate WIPO PatentScope, handle CAPTCHAs,
click the Documents tab, and download RO/101 PDFs.

Provides two modes:
  - PatentBrowser class: single-page headed mode for small runs (< 50 rows)
  - Browser pool functions: multi-page headless mode for pipeline (50+ rows)
"""
import re
import time
import tempfile
import threading
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

try:
    from shared.pacing import default_pacer
except Exception:  # shared.pacing should always import, but be defensive
    default_pacer = None


def _pace():
    """Apply request pacing before every outbound navigation."""
    if default_pacer is not None:
        try:
            default_pacer.wait()
        except Exception:
            pass

DOWNLOADS_DIR = Path(tempfile.gettempdir()) / "pct_pdfs"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# Resources to block — saves ~70% bandwidth per page
_BLOCKED_TYPES = {"image", "stylesheet", "font", "media"}


class BrowserStopRequested(RuntimeError):
    """Raised when the current browser run is force-stopped."""


# High-confidence markers only. Generic strings like "captcha", "challenge",
# or "please select" appear in normal WIPO page markup (dropdown placeholders,
# JS variable names, CSS classes) and used to trigger false-positive banners.
CAPTCHA_TEXT_MARKERS = [
    "pscaptchaform",
    "verify you are human",
    "please verify you are not a robot",
    "are you a human",
]

# DOM selectors that unambiguously identify an active CAPTCHA challenge.
# We additionally require the matched element to be visible before firing.
CAPTCHA_SELECTORS = [
    "#psCaptchaForm",
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "div.g-recaptcha",
    "div.h-captcha",
]


def _play_captcha_alert():
    """Best-effort local alert on the host machine."""
    if not HAS_WINSOUND:
        return
    try:
        winsound.MessageBeep()
    except Exception:
        pass


def _content_has_captcha_markers(content):
    haystack = (content or "").lower()
    return any(marker in haystack for marker in CAPTCHA_TEXT_MARKERS)


def _page_has_captcha_selectors(page):
    """Return True only when a CAPTCHA element is actually visible on the page.
    Hidden/leftover DOM nodes (e.g. preloaded recaptcha scripts) do not count.
    """
    for selector in CAPTCHA_SELECTORS:
        try:
            locator = page.locator(selector)
            count = locator.count()
        except Exception:
            continue
        for idx in range(min(count, 5)):
            try:
                if locator.nth(idx).is_visible():
                    return True
            except Exception:
                continue
    return False


def _title_looks_like_captcha(page):
    try:
        title = (page.title() or "").lower()
    except Exception:
        return False
    # Be strict — only obvious challenge pages, not pages with "captcha" in a
    # subtitle or breadcrumb.
    return (
        title.startswith("captcha")
        or "human verification" in title
        or "are you human" in title
        or title == "challenge"
    )


def _is_captcha_present(page, content=""):
    if _content_has_captcha_markers(content):
        return True
    if _title_looks_like_captcha(page):
        return True
    return _page_has_captcha_selectors(page)


def _solve_if_captcha(page, on_step=None, label="post-action"):
    """If a captcha is visible on the page right now, invoke the solver
    synchronously. Returns True when the page is captcha-free (either no
    captcha was present, or the solver cleared it). Returns False only when
    a captcha existed and every solver tier failed.
    """
    try:
        content = page.content()
    except Exception:
        return True  # if we can't read content, no point invoking the solver

    if not _is_captcha_present(page, content):
        return True

    step = on_step or (lambda *_a, **_k: None)
    step(f"[Browser] CAPTCHA detected after {label} — delegating to solver")

    if default_pacer is not None:
        try:
            default_pacer.report_captcha()
        except Exception:
            pass

    try:
        from .captcha_solver import solve_captcha
    except Exception as e:
        step(f"[Browser] Could not import captcha solver: {e}")
        return False

    try:
        url = page.url
    except Exception:
        url = ""
    try:
        return solve_captcha(page, on_step=on_step, source_url=url)
    except Exception as e:
        step(f"[Browser] Captcha solver crashed at {label}: {e}")
        return False


def _route_handler(route):
    """Abort non-essential resources to speed up page loads.
    Exception: always allow captcha/challenge images through — the solver
    agent needs to see them to OCR or vision-classify the challenge.
    """
    req = route.request
    if req.resource_type in _BLOCKED_TYPES:
        url_lower = (req.url or "").lower()
        if "captcha" in url_lower or "challenge" in url_lower or "recaptcha" in url_lower or "hcaptcha" in url_lower:
            route.continue_()
            return
        route.abort()
    else:
        route.continue_()


def _launch_browser(playwright, headless=True, per_context=False):
    """
    Launch a browser that WIPO is more likely to accept.
    Headed mode prefers real installed browser channels.
    Honors the shared proxy pool (Tor / user-supplied list) when configured.

    per_context=True: launch with the Chromium "per-context" proxy sentinel so
    that each browser context can later be given its OWN proxy (its own exit
    IP). This is what lets the pool spread WIPO load across many IPs. When the
    proxy pool is not configured we skip this and behave exactly as before.
    """
    proxy = None
    try:
        from shared import proxy_pool
        if per_context and proxy_pool.enabled():
            # Chromium requires a launch-level proxy to allow per-context
            # overrides; the "per-context" sentinel means "no proxy at launch,
            # each context supplies its own".
            proxy = {"server": "per-context"}
        else:
            proxy = proxy_pool.get_proxy()
    except Exception:
        proxy = None

    attempts = []
    if headless:
        attempts.append({"headless": True})
    else:
        attempts.extend([
            {"channel": "chrome", "headless": False},
            {"channel": "msedge", "headless": False},
            {"headless": False},
        ])

    base_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]

    last_error = None
    for launch_kwargs in attempts:
        if proxy:
            launch_kwargs = {**launch_kwargs, "proxy": proxy}
        try:
            return playwright.chromium.launch(**launch_kwargs, args=base_args)
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Could not launch Chromium for WIPO: {last_error}")


# ---------------------------------------------------------------------------
# Browser Pool — one browser, N pages for parallel pipeline
# ---------------------------------------------------------------------------
def create_browser_pool(n_pages=20, headless=True):
    """Create a single Playwright browser with N lightweight pages.
    Blocks images/CSS/fonts for maximum speed.

    Returns (pw, browser, pages_list, proxies_list) where proxies_list[i] is
    the Playwright proxy dict assigned to pages_list[i] (or None). When the
    proxy pool is configured, EACH page gets its own proxy → its own exit IP,
    so WIPO's per-IP throttling is spread across the pool instead of hitting
    one address. When no pool is configured, every entry is None and behavior
    is identical to before.
    """
    if not HAS_PLAYWRIGHT:
        raise ImportError(
            "Playwright is required. "
            "Install with: pip install playwright && python -m playwright install chromium"
        )
    DOWNLOADS_DIR.mkdir(exist_ok=True)

    try:
        from shared import proxy_pool
        use_proxy = proxy_pool.enabled()
    except Exception:
        proxy_pool = None
        use_proxy = False

    pw = sync_playwright().start()
    browser = _launch_browser(pw, headless=headless, per_context=use_proxy)

    # Image/CSS/font blocking is OFF by default — empirically it broke the
    # WIPO documents tab in pool mode (every row returned not_found). Opt in
    # via PCT_POOL_BLOCK_RESOURCES=true when you've confirmed it works for
    # your setup.
    import os as _os
    block_resources = (
        (_os.getenv("PCT_POOL_BLOCK_RESOURCES") or "false").lower()
        in ("1", "true", "yes")
    )

    pages = []
    proxies = []
    for i in range(n_pages):
        worker_proxy = proxy_pool.get_proxy_for_worker(i) if use_proxy else None
        ctx_kwargs = dict(
            accept_downloads=True,
            viewport={"width": 1280, "height": 720},
            user_agent=UA,
            locale="en-US",
        )
        if worker_proxy:
            ctx_kwargs["proxy"] = worker_proxy
        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        if block_resources:
            # Aggressive bandwidth saving — but risky against WIPO.
            page.route("**/*", _route_handler)
        pages.append(page)
        proxies.append(worker_proxy)

    return pw, browser, pages, proxies


def close_browser_pool(pw, browser):
    """Safely close browser pool."""
    try:
        if browser:
            browser.close()
    except Exception:
        pass
    try:
        if pw:
            pw.stop()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Standalone fast-scraping — used by pipeline workers
# ---------------------------------------------------------------------------
def scrape_patent_fast(page, url, doc_id, on_step=None):
    """Scrape a patent page: navigate → find PDF URL → download.
    Returns (pdf_path_or_None, captcha_detected).
    """
    # Navigate (1 retry)
    for attempt in range(2):
        _pace()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return None, False

        # Bumped from 20s to 60s: under parallel-pool load WIPO serves
        # pages slower; 20s wasn't enough so every row was timing out and
        # find_pdf_url ran on a half-loaded page → returned None → not_found.
        loaded, captcha = wait_for_content_fast(page, timeout=60, on_step=on_step)
        if captcha:
            return None, True
        if loaded:
            break
    else:
        return None, False

    # Click Documents tab — minimal wait
    try:
        docs_tab = page.locator("a", has_text="Documents").first
        docs_tab.wait_for(state="visible", timeout=5000)
        docs_tab.click()
        page.wait_for_timeout(800)
    except Exception:
        return None, False

    # WIPO sometimes serves a captcha specifically when the Documents tab is
    # clicked. If so, run the solver before giving up.
    if not _solve_if_captcha(page, on_step=on_step, label="Documents click"):
        return None, True

    # Find PDF URL
    pdf_url = find_pdf_url(page)
    if not pdf_url:
        # Diagnostic: when nothing is found, log what WIPO actually served.
        # Most useful when not_found rate spikes — tells us if pages are
        # genuinely empty (rate-limited), captcha-walled, or just lacking
        # any RO/101 / 306 / Request-form document.
        if callable(on_step):
            try:
                _diag_log_empty(page, on_step, "scrape_patent_fast")
            except Exception:
                pass
        return None, False

    # Download PDF
    pdf_path = download_pdf_fast(page, pdf_url, doc_id)
    return pdf_path, False


def scrape_pdf_url_only(page, url, on_step=None):
    """Scrape a patent page and return ONLY the PDF URL (no download).
    Used for 3-stage pipeline where download is separate.
    Returns (pdf_url_or_None, cookies_dict, captcha_detected, reason).

    `reason` is "" on success and one of these strings on miss:
      - "nav_failed"   : page.goto() threw both attempts (network/timeout)
      - "load_timeout" : page never produced the PCT Biblio marker
      - "docs_tab"     : Documents tab was not visible/clickable
      - "no_pdf_row"   : page loaded fully but no RO/101/306/Request-form PDF
      - "throttled"    : page loaded but biblio missing AND tr_count==0 — WIPO empty/throttled response
    The retry pass uses this to decide which rows are worth re-scraping.
    """
    for attempt in range(2):
        _pace()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return None, {}, False, "nav_failed"

        # Same 60s bump as scrape_patent_fast — pool mode needs the
        # extra patience under parallel-load throttling from WIPO.
        loaded, captcha = wait_for_content_fast(page, timeout=60, on_step=on_step)
        if captcha:
            return None, {}, True, "captcha"
        if loaded:
            break
    else:
        return None, {}, False, "load_timeout"

    try:
        docs_tab = page.locator("a", has_text="Documents").first
        docs_tab.wait_for(state="visible", timeout=5000)
        docs_tab.click()
        page.wait_for_timeout(800)
    except Exception:
        return None, {}, False, "docs_tab"

    # Solve any captcha that appeared specifically after the Documents click.
    if not _solve_if_captcha(page, on_step=on_step, label="Documents click"):
        return None, {}, True, "captcha"

    pdf_url = find_pdf_url(page)
    if not pdf_url:
        if callable(on_step):
            try:
                _diag_log_empty(page, on_step, "scrape_pdf_url_only")
            except Exception:
                pass
        # Classify: throttled (empty page) vs. genuine no-PDF (page loaded fine
        # but the document list lacks RO/101 / 306 / Request form).
        miss_reason = _classify_no_pdf(page)
        return None, {}, False, miss_reason

    if not pdf_url.startswith("http"):
        pdf_url = "https://patentscope.wipo.int" + pdf_url

    # Extract cookies for separate download
    cookies = {}
    for c in page.context.cookies():
        cookies[c["name"]] = c["value"]

    return pdf_url, cookies, False, ""


def _classify_no_pdf(page):
    """When find_pdf_url returns None, decide if this is a real not_found
    or a WIPO throttle/empty response. Used to drive the retry pass:
    "throttled" rows are worth retrying with reduced concurrency;
    "no_pdf_row" rows are genuinely missing the document and not worth
    re-scraping at all.
    """
    try:
        content = page.content() or ""
    except Exception:
        content = ""
    try:
        tr_count = page.locator("tr").count()
    except Exception:
        tr_count = -1
    has_biblio = "PCT Biblio" in content or "detailMainForm" in content
    if not has_biblio and tr_count <= 0:
        return "throttled"
    return "no_pdf_row"


def wait_for_content_fast(page, timeout=20, on_step=None):
    """Wait for patent page content. Returns (loaded, captcha_detected).
    Fast polling with 300ms intervals. On a confirmed captcha (2 hits) the
    solver agent is invoked; if it clears the challenge we keep polling and
    eventually return (True, False).
    """
    deadline = time.time() + timeout
    captcha_streak = 0
    solver_attempted = False
    step = on_step or (lambda *_a, **_k: None)

    while time.time() < deadline:
        try:
            content = page.content()
        except Exception:
            time.sleep(0.3)
            continue

        if "PCT Biblio" in content or "detailMainForm" in content:
            return True, False

        if _is_captcha_present(page, content):
            captcha_streak += 1
            if captcha_streak >= 2 and not solver_attempted:
                solver_attempted = True
                if _invoke_solver_pool(page, step, deadline):
                    captcha_streak = 0
                    continue
                # Solver gave up — bubble the captcha signal so the caller
                # can re-queue and apply pipeline-level backoff.
                return False, True
            time.sleep(0.3)
            continue

        captcha_streak = 0

        if "403" in (page.title() or ""):
            try:
                page.reload(wait_until="domcontentloaded", timeout=8000)
            except Exception:
                pass
            continue

        time.sleep(0.3)

    return False, False


def _invoke_solver_pool(page, step, deadline):
    """Pool-mode solver invocation. Same contract as PatentBrowser._invoke_solver
    but for the standalone page objects used by pipeline workers.
    """
    if default_pacer is not None:
        try:
            default_pacer.report_captcha()
        except Exception:
            pass
    try:
        from .captcha_solver import solve_captcha
    except Exception as e:
        step(f"[Browser] Could not import captcha solver: {e}")
        return False

    remaining = max(15, int(deadline - time.time()))
    try:
        url = page.url
    except Exception:
        url = ""
    try:
        return solve_captcha(page, on_step=step, max_seconds=remaining, source_url=url)
    except Exception as e:
        step(f"[Browser] Captcha solver crashed: {e}")
        return False


def _diag_log_empty(page, on_step, where):
    """When find_pdf_url returns None, log what kind of page WIPO served.
    Helps distinguish 'legitimately no RO/101 PDF' from 'rate-limited /
    blocked / empty page'. Used only on failure — zero cost on success.
    """
    try:
        title = page.title() or ""
    except Exception:
        title = "?"
    try:
        tr_count = page.locator("tr").count()
    except Exception:
        tr_count = -1
    try:
        has_biblio = "PCT Biblio" in (page.content() or "")
    except Exception:
        has_biblio = False
    on_step(
        f"[Diag:{where}] no PDF — title={title!r}, tr_count={tr_count}, "
        f"has_biblio={has_biblio} (if tr_count=0 and !has_biblio, WIPO likely "
        f"rate-throttled this request — back off the speed level)"
    )


def find_pdf_url(page):
    """Find RO/101, 306, or Request form PDF link.  Returns URL or None."""
    for term in ["RO/101", "306", "Request form"]:
        try:
            rows = page.locator("tr", has_text=term)
            if rows.count() > 0:
                pdf_links = rows.first.locator("a", has_text="PDF")
                if pdf_links.count() > 0:
                    href = pdf_links.first.get_attribute("href")
                    if href:
                        return href
        except Exception:
            pass
    return None


def _requests_proxies(proxy):
    """Convert a Playwright proxy dict to a requests `proxies=` mapping.
    Returns None when no proxy (direct connection). SOCKS URLs require the
    optional PySocks dependency (requests[socks]).
    """
    if not proxy or not proxy.get("server"):
        return None
    server = proxy["server"]
    if server == "per-context":
        return None
    # For SOCKS (Tor), use socks5h so DNS resolves at the exit node (remote
    # DNS) — the standard, leak-free way to proxy requests through Tor.
    if server.startswith("socks5://"):
        server = "socks5h://" + server[len("socks5://"):]
    user = proxy.get("username")
    pw = proxy.get("password")
    if user and "://" in server:
        scheme, rest = server.split("://", 1)
        server = f"{scheme}://{user}:{pw}@{rest}"
    return {"http": server, "https": server}


def download_pdf_standalone(pdf_url, cookies, doc_id, proxy=None):
    """Download a PDF using plain HTTP (no browser needed).
    Called from download worker threads.  Returns file path or None.

    When `proxy` is supplied we route the download through the SAME exit IP as
    the browser context that discovered the URL — WIPO may tie the download to
    the session's IP. If the proxied attempt fails we fall back to a direct
    download so proxy hiccups never regress the pre-proxy behavior.
    """
    import requests as req

    safe_name = re.sub(r"[^\w\-]", "_", doc_id)
    save_path = DOWNLOADS_DIR / f"{safe_name}.pdf"

    proxies = _requests_proxies(proxy)
    attempts = [proxies] if proxies else [None]
    if proxies:
        attempts.append(None)  # fall back to direct if the proxy download fails

    for proxy_map in attempts:
        try:
            session = req.Session()
            for name, value in cookies.items():
                session.cookies.set(name, value)
            session.headers.update({"User-Agent": UA})
            if proxy_map:
                session.proxies.update(proxy_map)

            resp = session.get(pdf_url, timeout=20)
            if resp.status_code == 200 and len(resp.content) > 500:
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                return str(save_path)
        except Exception:
            continue
    return None


def download_pdf_fast(page, pdf_url, doc_id):
    """Download a PDF using browser cookies.  Returns file path or None."""
    if not pdf_url.startswith("http"):
        pdf_url = "https://patentscope.wipo.int" + pdf_url

    cookies = {}
    for c in page.context.cookies():
        cookies[c["name"]] = c["value"]

    return download_pdf_standalone(pdf_url, cookies, doc_id)


class PatentBrowser:
    """Manages a Playwright browser session for WIPO PatentScope scraping."""

    def __init__(self, headless=False, on_step=None, stop_requested=None):
        self.headless = headless
        self.on_step = on_step
        self.stop_requested = stop_requested or (lambda: False)
        self._force_stop = threading.Event()
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()

    def is_stop_requested(self):
        return self._force_stop.is_set() or bool(self.stop_requested())

    def _check_stop(self):
        if self.is_stop_requested():
            raise BrowserStopRequested("Stop requested")

    def start(self):
        """Launch browser and create a page."""
        self._check_stop()
        if not HAS_PLAYWRIGHT:
            raise ImportError(
                "Playwright is required for WIPO scraping. "
                "Install with: pip install playwright && python -m playwright install chromium"
            )
        DOWNLOADS_DIR.mkdir(exist_ok=True)

        self._pw = sync_playwright().start()
        self._browser = _launch_browser(self._pw, headless=self.headless)
        self._context = self._browser.new_context(
            accept_downloads=True,
            viewport={"width": 1366, "height": 768},
            user_agent=UA,
            locale="en-US",
        )
        self._page = self._context.new_page()
        # Remove webdriver detection flag
        self._page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        if self.on_step:
            self.on_step("[Browser] Chromium launched — WIPO browser ready")

    def force_stop(self):
        """Request that the current browser job stop at the next safe check."""
        if self._force_stop.is_set():
            return
        self._force_stop.set()
        if self.on_step:
            self.on_step("[Browser] Stop requested - finishing the current browser call and closing safely")

    def close(self):
        """Close browser and cleanup."""
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None

    def scrape_patent(self, url, doc_id, on_step=None):
        """
        Full pipeline for one patent:
        1. Navigate to patent page
        2. Wait for content (handle CAPTCHA)
        3. Click Documents tab
        4. Find RO/101 PDF
        5. Download the PDF
        Returns path to downloaded PDF, or None.
        """
        step = on_step or self.on_step or (lambda m: None)
        page = self._page
        self._check_stop()
        if not page:
            step("[Browser] ERROR: Browser not started")
            return None

        # --- Step 1: Navigate (with retry) ---
        loaded = False
        for attempt in range(2):
            self._check_stop()
            _pace()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=8000)
            except Exception as e:
                if self.is_stop_requested():
                    raise BrowserStopRequested("Stop requested")
                step(f"[Browser] Navigation failed (attempt {attempt+1}): {e}")
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                return None

            # --- Step 2: Wait for content ---
            if self._wait_for_content(timeout=20, on_step=step):
                loaded = True
                break
            elif attempt == 0:
                step("[Browser] Retrying page load...")
                time.sleep(0.5)

        if not loaded:
            step("[Browser] Page did not load after retries")
            return None

        # --- Step 3: Click Documents tab ---
        try:
            self._check_stop()
            docs_tab = page.locator("a", has_text="Documents").first
            docs_tab.wait_for(state="visible", timeout=3000)
            docs_tab.click()
            page.wait_for_timeout(800)
            step("[Browser] Documents tab opened")
        except Exception as e:
            if self.is_stop_requested():
                raise BrowserStopRequested("Stop requested")
            step(f"[Browser] Could not open Documents tab: {e}")
            return None

        # WIPO sometimes serves a captcha specifically after the Documents
        # click. Run the solver before trying to find the PDF link.
        if not _solve_if_captcha(page, on_step=step, label="Documents click"):
            step("[Browser] Captcha after Documents click could not be solved")
            return None

        # --- Step 4: Find RO/101 PDF link ---
        pdf_url = self._find_ro101_pdf(on_step=step)
        if not pdf_url:
            step("[Browser] No RO/101, 306, or Request form PDF found")
            return None

        # --- Step 5: Download the PDF ---
        pdf_path = self._download_pdf(pdf_url, doc_id, on_step=step)
        return pdf_path

    def _wait_for_content(self, timeout=120, on_step=None):
        """Wait for the patent page to fully load. On confirmed CAPTCHA the
        captcha_solver sub-agent (agents/pct_agent/captcha_solver/) is
        invoked synchronously — it walks through DIY OCR, OpenAI vision,
        and manual fallback tiers and emits its own UI events. We just
        resume polling once it returns.
        """
        step = on_step or (lambda m: None)
        deadline = time.time() + timeout
        # Require 2 consecutive positive detections before delegating to the
        # solver — this debounces transient false positives during page load.
        captcha_streak = 0
        CAPTCHA_CONFIRM_HITS = 2
        solver_attempted = False

        while time.time() < deadline:
            self._check_stop()
            try:
                content = self._page.content()
            except Exception:
                if self.is_stop_requested():
                    raise BrowserStopRequested("Stop requested")
                time.sleep(0.25)
                continue

            # Success: patent content loaded
            if "PCT Biblio" in content or "detailMainForm" in content:
                return True

            # CAPTCHA candidate
            if _is_captcha_present(self._page, content):
                captcha_streak += 1
                if captcha_streak >= CAPTCHA_CONFIRM_HITS and not solver_attempted:
                    solver_attempted = True
                    if not self._invoke_solver(step, deadline):
                        return False
                    # Solver finished. Let the loop poll again and confirm
                    # content; reset streak so any future captcha gets its
                    # own debounce.
                    captcha_streak = 0
                    continue
                time.sleep(0.5)
                continue

            # No captcha on this poll — reset streak so a single transient
            # match doesn't latch.
            captcha_streak = 0

            # 403 error
            if "403" in (self._page.title() or ""):
                step("[Browser] Got 403 Forbidden — retrying...")
                time.sleep(0.5)
                try:
                    self._page.reload(wait_until="domcontentloaded", timeout=5000)
                except Exception:
                    pass
                continue

            # Page might be reloading (the setTimeout(reload) trick)
            time.sleep(0.25)

        return False

    def _invoke_solver(self, step, deadline):
        """Call the captcha solver synchronously. Returns True if the solver
        believes the challenge is cleared (caller should keep polling), or
        False if every tier failed (caller should abandon this row).
        """
        if default_pacer is not None:
            try:
                default_pacer.report_captcha()
            except Exception:
                pass
        try:
            from .captcha_solver import solve_captcha
        except Exception as e:
            step(f"[Browser] Could not import captcha solver: {e} — falling back to manual beep")
            _play_captcha_alert()
            return False

        remaining = max(15, int(deadline - time.time()))
        try:
            url = self._page.url
        except Exception:
            url = ""
        try:
            return solve_captcha(
                self._page, on_step=step,
                max_seconds=remaining, source_url=url,
            )
        except Exception as e:
            step(f"[Browser] Captcha solver crashed: {e}")
            return False

    def _find_ro101_pdf(self, on_step=None):
        """Find the RO/101, 306, or Request form PDF link on the Documents tab.
        Searches multiple document types in priority order."""
        step = on_step or (lambda m: None)
        page = self._page

        # Search terms in priority order
        search_terms = ["RO/101", "306", "Request form"]

        for term in search_terms:
            self._check_stop()
            try:
                rows = page.locator("tr", has_text=term)
                if rows.count() > 0:
                    row = rows.first
                    pdf_links = row.locator("a", has_text="PDF")
                    if pdf_links.count() > 0:
                        href = pdf_links.first.get_attribute("href")
                        if href:
                            step(f"[Browser] Found '{term}' PDF link")
                            return href
                        return "__CLICK_DOWNLOAD__"
            except Exception as e:
                if self.is_stop_requested():
                    raise BrowserStopRequested("Stop requested")
                step(f"[Browser] Error searching for '{term}': {e}")

        return None

    def _download_pdf(self, pdf_url, doc_id, on_step=None):
        """Download a PDF file. Returns the saved file path or None."""
        import requests as req

        step = on_step or (lambda m: None)
        page = self._page

        safe_name = re.sub(r"[^\w\-]", "_", doc_id)
        save_path = DOWNLOADS_DIR / f"{safe_name}.pdf"

        try:
            self._check_stop()
            if pdf_url == "__CLICK_DOWNLOAD__":
                # No href — try clicking and intercepting the navigation
                ro101_rows = None
                for term in ["RO/101", "306", "Request form"]:
                    self._check_stop()
                    candidate = page.locator("tr", has_text=term)
                    if candidate.count() > 0:
                        ro101_rows = candidate
                        break
                if not ro101_rows or ro101_rows.count() == 0:
                    step("[Browser] Could not find document row for click-download")
                    return None
                pdf_link = ro101_rows.first.locator("a", has_text="PDF").first

                # Try to get href via JS
                href = pdf_link.evaluate("el => el.href || el.getAttribute('onclick') || ''")
                if href and href.startswith("http"):
                    pdf_url = href
                else:
                    # Click and try to capture download
                    try:
                        self._check_stop()
                        with page.expect_download(timeout=15000) as dl_info:
                            pdf_link.click()
                        download = dl_info.value
                        download.save_as(str(save_path))
                        step(f"[Browser] PDF saved: {save_path.name}")
                        return str(save_path)
                    except Exception:
                        if self.is_stop_requested():
                            raise BrowserStopRequested("Stop requested")
                        step("[Browser] Click-download failed, trying direct fetch")
                        return None

            # Make URL absolute
            if not pdf_url.startswith("http"):
                pdf_url = "https://patentscope.wipo.int" + pdf_url

            # Download using requests with browser cookies
            session = req.Session()
            for cookie in self._context.cookies():
                self._check_stop()
                session.cookies.set(
                    cookie["name"], cookie["value"],
                    domain=cookie.get("domain", ""),
                )
            session.headers.update({"User-Agent": UA, "Referer": page.url})

            self._check_stop()
            resp = session.get(pdf_url, timeout=(10, 10), stream=True)
            self._check_stop()
            if resp.status_code == 200:
                total_bytes = 0
                with open(save_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        self._check_stop()
                        if not chunk:
                            continue
                        f.write(chunk)
                        total_bytes += len(chunk)
                if total_bytes > 500:
                    step(f"[Browser] PDF saved: {save_path.name} ({total_bytes} bytes)")
                    return str(save_path)
                step(f"[Browser] PDF download returned too little data ({total_bytes} bytes)")
                return None
            else:
                step(f"[Browser] PDF download returned {resp.status_code}")
                return None

        except Exception as e:
            if self.is_stop_requested():
                raise BrowserStopRequested("Stop requested")
            step(f"[Browser] PDF download failed: {e}")
            return None
