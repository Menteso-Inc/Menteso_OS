"""
PCT Sub-Agent: WIPO Scraper
Downloads Excel from WIPO PatentScope weekly browse page,
or processes a user-uploaded Excel to visit each patent detail URL.
"""
import os
import re
import time
import tempfile
import requests
from pathlib import Path
from urllib.parse import urljoin

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from playwright.async_api import async_playwright
    HAS_ASYNC_PLAYWRIGHT = True
except ImportError:
    HAS_ASYNC_PLAYWRIGHT = False

WIPO_BROWSE_URL = "https://patentscope.wipo.int/search/en/resultWeeklyBrowse.jsf"
WIPO_BASE = "https://patentscope.wipo.int"
WIPO_GAZETTE_SELECT = "#weeklyPublicationForm\\:currGazette\\:input"


def _launch_wipo_browser(playwright):
    """Launch a real browser channel that WIPO accepts."""
    attempts = [
        {"channel": "chrome", "headless": False},
        {"channel": "msedge", "headless": False},
        {"headless": False},
    ]
    last_error = None

    for launch_kwargs in attempts:
        try:
            browser = playwright.chromium.launch(**launch_kwargs)
            return browser
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Could not launch a supported browser for WIPO: {last_error}")


async def _launch_wipo_browser_async(playwright):
    """Async counterpart used by FastAPI endpoints."""
    attempts = [
        {"channel": "chrome", "headless": False},
        {"channel": "msedge", "headless": False},
        {"headless": False},
    ]
    last_error = None

    for launch_kwargs in attempts:
        try:
            browser = await playwright.chromium.launch(**launch_kwargs)
            return browser
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Could not launch a supported browser for WIPO: {last_error}")


def _normalize_gazettes(options):
    """Normalize native <select> options into API-friendly objects."""
    gazettes = []
    for option in options:
        value = (option.get("value") or "").strip()
        label = (option.get("label") or "").strip()
        if not value or not label:
            continue
        gazettes.append({"value": value, "label": label})
    return gazettes


def fetch_wipo_gazettes(on_step=None):
    """
    Read the available weekly gazette options from WIPO.
    Returns a list like: [{"value": "18/2026", "label": "18/2026 (30.04.2026)"}]
    """
    if not HAS_PLAYWRIGHT:
        raise ImportError(
            "Playwright is required for WIPO browse automation. "
            "Install with: pip install playwright && python -m playwright install chromium"
        )

    if on_step:
        on_step("[Scraper] Opening WIPO weekly browse page...")

    with sync_playwright() as pw:
        browser = _launch_wipo_browser(pw)
        try:
            context = browser.new_context(accept_downloads=True, locale="en-US")
            page = context.new_page()
            page.goto(WIPO_BROWSE_URL, wait_until="networkidle", timeout=90000)
            page.wait_for_selector(WIPO_GAZETTE_SELECT, timeout=30000)

            select = page.locator(WIPO_GAZETTE_SELECT)
            options = select.locator("option").evaluate_all(
                """els => els.map(el => ({ value: el.value, label: el.textContent || "" }))"""
            )
            gazettes = _normalize_gazettes(options)

            if on_step:
                on_step(f"[Scraper] Loaded {len(gazettes)} WIPO gazette options")

            return gazettes
        finally:
            browser.close()


async def fetch_wipo_gazettes_async(on_step=None):
    """
    Async variant for web request handlers that cannot use the sync API.
    """
    if not HAS_ASYNC_PLAYWRIGHT:
        raise ImportError(
            "Playwright is required for WIPO browse automation. "
            "Install with: pip install playwright && python -m playwright install chromium"
        )

    if on_step:
        on_step("[Scraper] Opening WIPO weekly browse page...")

    async with async_playwright() as pw:
        browser = await _launch_wipo_browser_async(pw)
        try:
            context = await browser.new_context(accept_downloads=True, locale="en-US")
            page = await context.new_page()
            await page.goto(WIPO_BROWSE_URL, wait_until="networkidle", timeout=90000)
            await page.wait_for_selector(WIPO_GAZETTE_SELECT, timeout=30000)

            options = await page.locator(f"{WIPO_GAZETTE_SELECT} option").evaluate_all(
                """els => els.map(el => ({ value: el.value, label: el.textContent || "" }))"""
            )
            gazettes = _normalize_gazettes(options)

            if on_step:
                on_step(f"[Scraper] Loaded {len(gazettes)} WIPO gazette options")

            return gazettes
        finally:
            await browser.close()


def download_wipo_excel(filters=None, gazette=None, on_step=None):
    """
    Download the weekly browse Excel from WIPO PatentScope.
    Returns path to downloaded Excel file.
    """
    if not HAS_PLAYWRIGHT:
        raise ImportError(
            "Playwright is required for WIPO browse automation. "
            "Install with: pip install playwright && python -m playwright install chromium"
        )

    if on_step:
        on_step("[Scraper] Connecting to WIPO PatentScope...")

    with sync_playwright() as pw:
        browser = _launch_wipo_browser(pw)
        try:
            context = browser.new_context(accept_downloads=True, locale="en-US")
            page = context.new_page()
            page.goto(WIPO_BROWSE_URL, wait_until="networkidle", timeout=90000)
            page.wait_for_selector(WIPO_GAZETTE_SELECT, timeout=30000)

            select = page.locator(WIPO_GAZETTE_SELECT)
            options = select.locator("option").evaluate_all(
                """els => els.map(el => ({ value: el.value, label: el.textContent || "" }))"""
            )
            gazettes = _normalize_gazettes(options)
            valid_values = {item["value"] for item in gazettes}

            selected_gazette = gazette or (gazettes[0]["value"] if gazettes else None)
            if not selected_gazette:
                raise RuntimeError("No WIPO gazette options were found on the page")
            if selected_gazette not in valid_values:
                raise ValueError(f"Gazette '{selected_gazette}' is not available on WIPO")

            if on_step:
                on_step(f"[Scraper] Selected gazette: {selected_gazette}")

            select.select_option(selected_gazette)
            page.wait_for_timeout(3000)

            if on_step:
                on_step("[Scraper] Starting Excel download...")

            download_link = page.locator("a", has_text="Excel Download").first
            download_link.wait_for(state="visible", timeout=60000)
            download_link.scroll_into_view_if_needed(timeout=60000)
            with page.expect_download(timeout=60000) as download_info:
                download_link.click(timeout=60000, force=True)
            download = download_info.value

            output_dir = Path(__file__).parent.parent.parent / "uploads"
            output_dir.mkdir(exist_ok=True)
            safe_week = selected_gazette.replace("/", "-")
            suffix = Path(download.suggested_filename or "resultList.xls").suffix or ".xls"
            output_path = output_dir / f"wipo_weekly_browse_{safe_week}{suffix}"
            download.save_as(str(output_path))

            if on_step:
                on_step(
                    f"[Scraper] Excel downloaded: {output_path.name} "
                    f"({output_path.stat().st_size} bytes)"
                )

            return str(output_path)
        finally:
            browser.close()


def scrape_patent_detail(url, session=None, on_step=None):
    """
    Visit a patent detail page and find the Documents tab.
    Look for RO/101 Request Form or Form 306 PDF.
    Returns the PDF download URL or None.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        page_html = resp.text

        # Look for document links — RO/101 or 306 patterns
        pdf_patterns = [
            re.compile(r'href=["\']([^"\']*)["\'][^>]*>.*?RO/?101.*?Request\s*form', re.IGNORECASE | re.DOTALL),
            re.compile(r'href=["\']([^"\']*)["\'][^>]*>.*?\(RO/?101\)', re.IGNORECASE | re.DOTALL),
            re.compile(r'href=["\']([^"\']*)["\'][^>]*>.*?306', re.IGNORECASE | re.DOTALL),
            re.compile(r'href=["\']([^"\']*\.pdf)["\']', re.IGNORECASE),
        ]

        for pattern in pdf_patterns:
            matches = pattern.findall(page_html)
            if matches:
                pdf_url = matches[0]
                if not pdf_url.startswith("http"):
                    pdf_url = urljoin(WIPO_BASE, pdf_url)
                return pdf_url

        # Try documents tab URL pattern
        # WIPO detail pages often have tabs like ?docId=...&tab=documents
        if "docId=" in url and "tab=" not in url:
            doc_tab_url = url + "&tab=documents" if "?" in url else url + "?tab=documents"
            resp2 = session.get(doc_tab_url, timeout=30)
            if resp2.ok:
                for pattern in pdf_patterns:
                    matches = pattern.findall(resp2.text)
                    if matches:
                        pdf_url = matches[0]
                        if not pdf_url.startswith("http"):
                            pdf_url = urljoin(WIPO_BASE, pdf_url)
                        return pdf_url

    except Exception as e:
        if on_step:
            on_step(f"[Scraper] Error scraping {url}: {e}")

    return None


def download_pdf(pdf_url, doc_id, session=None, on_step=None):
    """Download a PDF from WIPO and save to temp directory. Returns file path."""
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    try:
        resp = session.get(pdf_url, timeout=60)
        resp.raise_for_status()

        output_dir = Path(tempfile.gettempdir()) / "pct_pdfs"
        output_dir.mkdir(exist_ok=True)
        safe_name = re.sub(r'[^\w\-]', '_', doc_id)
        output_path = output_dir / f"{safe_name}.pdf"

        with open(output_path, "wb") as f:
            f.write(resp.content)

        return str(output_path)

    except Exception as e:
        if on_step:
            on_step(f"[Scraper] PDF download failed for {doc_id}: {e}")
        return None
