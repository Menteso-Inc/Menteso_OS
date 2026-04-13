"""
PCT Sub-Agent: Browser Automation
Uses Playwright (headed mode) to navigate WIPO PatentScope,
handle CAPTCHAs, click the Documents tab, and download RO/101 PDFs.

The browser opens visibly so the user can solve CAPTCHAs when they appear.
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
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
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
            step("[Browser] No [RO/101] Request form PDF found")
            return None

        step(f"[Browser] Found RO/101 PDF link")

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
        """Find the RO/101 Request form PDF link on the Documents tab."""
        step = on_step or (lambda m: None)
        page = self._page

        # Method 1: Find rows containing [RO/101] or "Request form"
        try:
            # Look for table rows with RO/101
            ro101_rows = page.locator("tr", has_text="RO/101")
            if ro101_rows.count() > 0:
                # Find the "View" PDF link in the first matching row
                row = ro101_rows.first
                pdf_links = row.locator("a", has_text="PDF")
                if pdf_links.count() > 0:
                    href = pdf_links.first.get_attribute("href")
                    if href:
                        return href
                    # If no href, we'll click and catch the download
                    return "__CLICK_DOWNLOAD__"
        except Exception as e:
            step(f"[Browser] Error finding RO/101: {e}")

        # Method 2: Look for "Request form" text
        try:
            request_rows = page.locator("tr", has_text="Request form")
            if request_rows.count() > 0:
                row = request_rows.first
                pdf_links = row.locator("a", has_text="PDF")
                if pdf_links.count() > 0:
                    href = pdf_links.first.get_attribute("href")
                    return href or "__CLICK_DOWNLOAD__"
        except Exception:
            pass

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
                ro101_rows = page.locator("tr", has_text="RO/101")
                if ro101_rows.count() == 0:
                    ro101_rows = page.locator("tr", has_text="Request form")
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
            session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": page.url,
            })

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
