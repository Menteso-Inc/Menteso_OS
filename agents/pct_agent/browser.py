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
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

DOWNLOADS_DIR = Path(tempfile.gettempdir()) / "pct_pdfs"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# Resources to block — saves ~70% bandwidth per page
_BLOCKED_TYPES = {"image", "stylesheet", "font", "media"}


def _route_handler(route):
    """Abort non-essential resources to speed up page loads."""
    if route.request.resource_type in _BLOCKED_TYPES:
        route.abort()
    else:
        route.continue_()


# ---------------------------------------------------------------------------
# Browser Pool — one browser, N pages for parallel pipeline
# ---------------------------------------------------------------------------
def create_browser_pool(n_pages=20, headless=True):
    """Create a single Playwright browser with N lightweight pages.
    Blocks images/CSS/fonts for maximum speed.
    Returns (pw, browser, pages_list).
    """
    if not HAS_PLAYWRIGHT:
        raise ImportError(
            "Playwright is required. "
            "Install with: pip install playwright && python -m playwright install chromium"
        )
    DOWNLOADS_DIR.mkdir(exist_ok=True)

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )

    pages = []
    for _ in range(n_pages):
        ctx = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 720},
            user_agent=UA,
            locale="en-US",
        )
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        # Block images, CSS, fonts — massive speed boost
        page.route("**/*", _route_handler)
        pages.append(page)

    return pw, browser, pages


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
def scrape_patent_fast(page, url, doc_id):
    """Scrape a patent page: navigate → find PDF URL → download.
    Returns (pdf_path_or_None, captcha_detected).
    """
    # Navigate (1 retry)
    for attempt in range(2):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return None, False

        loaded, captcha = wait_for_content_fast(page, timeout=20)
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

    # Find PDF URL
    pdf_url = find_pdf_url(page)
    if not pdf_url:
        return None, False

    # Download PDF
    pdf_path = download_pdf_fast(page, pdf_url, doc_id)
    return pdf_path, False


def scrape_pdf_url_only(page, url):
    """Scrape a patent page and return ONLY the PDF URL (no download).
    Used for 3-stage pipeline where download is separate.
    Returns (pdf_url_or_None, cookies_dict, captcha_detected).
    """
    for attempt in range(2):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return None, {}, False

        loaded, captcha = wait_for_content_fast(page, timeout=20)
        if captcha:
            return None, {}, True
        if loaded:
            break
    else:
        return None, {}, False

    try:
        docs_tab = page.locator("a", has_text="Documents").first
        docs_tab.wait_for(state="visible", timeout=5000)
        docs_tab.click()
        page.wait_for_timeout(800)
    except Exception:
        return None, {}, False

    pdf_url = find_pdf_url(page)
    if not pdf_url:
        return None, {}, False

    if not pdf_url.startswith("http"):
        pdf_url = "https://patentscope.wipo.int" + pdf_url

    # Extract cookies for separate download
    cookies = {}
    for c in page.context.cookies():
        cookies[c["name"]] = c["value"]

    return pdf_url, cookies, False


def wait_for_content_fast(page, timeout=20):
    """Wait for patent page content.  Returns (loaded, captcha_detected).
    Fast polling with 300ms intervals.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            content = page.content()
        except Exception:
            time.sleep(0.3)
            continue

        if "PCT Biblio" in content or "detailMainForm" in content:
            return True, False
        if "psCaptchaForm" in content or "Please select" in content:
            return False, True
        if "403" in (page.title() or ""):
            try:
                page.reload(wait_until="domcontentloaded", timeout=8000)
            except Exception:
                pass
            continue

        time.sleep(0.3)

    return False, False


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


def download_pdf_standalone(pdf_url, cookies, doc_id):
    """Download a PDF using plain HTTP (no browser needed).
    Called from download worker threads.  Returns file path or None.
    """
    import requests as req

    safe_name = re.sub(r"[^\w\-]", "_", doc_id)
    save_path = DOWNLOADS_DIR / f"{safe_name}.pdf"

    try:
        session = req.Session()
        for name, value in cookies.items():
            session.cookies.set(name, value)
        session.headers.update({"User-Agent": UA})

        resp = session.get(pdf_url, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 500:
            with open(save_path, "wb") as f:
                f.write(resp.content)
            return str(save_path)
    except Exception:
        pass
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

    def __init__(self, headless=False, on_step=None):
        self.headless = headless
        self.on_step = on_step
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()

    def start(self):
        """Launch browser and create a page."""
        if not HAS_PLAYWRIGHT:
            raise ImportError(
                "Playwright is required for WIPO scraping. "
                "Install with: pip install playwright && python -m playwright install chromium"
            )
        DOWNLOADS_DIR.mkdir(exist_ok=True)

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
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

    def close(self):
        """Close browser and cleanup."""
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
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
        if not page:
            step("[Browser] ERROR: Browser not started")
            return None

        # --- Step 1: Navigate (with retry) ---
        loaded = False
        for attempt in range(2):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                step(f"[Browser] Navigation failed (attempt {attempt+1}): {e}")
                if attempt == 0:
                    time.sleep(3)
                    continue
                return None

            # --- Step 2: Wait for content ---
            if self._wait_for_content(timeout=90, on_step=step):
                loaded = True
                break
            elif attempt == 0:
                step("[Browser] Retrying page load...")
                time.sleep(2)

        if not loaded:
            step("[Browser] Page did not load after retries")
            return None

        # --- Step 3: Click Documents tab ---
        try:
            docs_tab = page.locator("a", has_text="Documents").first
            docs_tab.wait_for(state="visible", timeout=10000)
            docs_tab.click()
            page.wait_for_timeout(3000)
            step("[Browser] Documents tab opened")
        except Exception as e:
            step(f"[Browser] Could not open Documents tab: {e}")
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
        """Wait for the patent page to fully load. Handles CAPTCHA."""
        step = on_step or (lambda m: None)
        deadline = time.time() + timeout
        captcha_warned = False

        while time.time() < deadline:
            try:
                content = self._page.content()
            except Exception:
                time.sleep(1)
                continue

            # Success: patent content loaded
            if "PCT Biblio" in content or "detailMainForm" in content:
                return True

            # CAPTCHA detected
            if "psCaptchaForm" in content or "Please select" in content:
                if not captcha_warned:
                    step("[Browser] CAPTCHA detected — please solve it in the browser window")
                    captcha_warned = True
                time.sleep(2)
                continue

            # 403 error
            if "403" in (self._page.title() or ""):
                step("[Browser] Got 403 Forbidden — retrying...")
                time.sleep(3)
                try:
                    self._page.reload(wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass
                continue

            # Page might be reloading (the setTimeout(reload) trick)
            time.sleep(2)

        return False

    def _find_ro101_pdf(self, on_step=None):
        """Find the RO/101, 306, or Request form PDF link on the Documents tab.
        Searches multiple document types in priority order."""
        step = on_step or (lambda m: None)
        page = self._page

        # Search terms in priority order
        search_terms = ["RO/101", "306", "Request form"]

        for term in search_terms:
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
            if pdf_url == "__CLICK_DOWNLOAD__":
                # No href — try clicking and intercepting the navigation
                ro101_rows = None
                for term in ["RO/101", "306", "Request form"]:
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
                        with page.expect_download(timeout=15000) as dl_info:
                            pdf_link.click()
                        download = dl_info.value
                        download.save_as(str(save_path))
                        step(f"[Browser] PDF saved: {save_path.name}")
                        return str(save_path)
                    except Exception:
                        step("[Browser] Click-download failed, trying direct fetch")
                        return None

            # Make URL absolute
            if not pdf_url.startswith("http"):
                pdf_url = "https://patentscope.wipo.int" + pdf_url

            # Download using requests with browser cookies
            session = req.Session()
            for cookie in self._context.cookies():
                session.cookies.set(
                    cookie["name"], cookie["value"],
                    domain=cookie.get("domain", ""),
                )
            session.headers.update({"User-Agent": UA, "Referer": page.url})

            resp = session.get(pdf_url, timeout=30)
            if resp.status_code == 200 and len(resp.content) > 500:
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                step(f"[Browser] PDF saved: {save_path.name} ({len(resp.content)} bytes)")
                return str(save_path)
            else:
                step(f"[Browser] PDF download returned {resp.status_code} ({len(resp.content)} bytes)")
                return None

        except Exception as e:
            step(f"[Browser] PDF download failed: {e}")
            return None
