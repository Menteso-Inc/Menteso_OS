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

WIPO_BROWSE_URL = "https://patentscope.wipo.int/search/en/resultWeeklyBrowse.jsf"
WIPO_BASE = "https://patentscope.wipo.int"


def download_wipo_excel(filters=None, on_step=None):
    """
    Download the weekly browse Excel from WIPO PatentScope.
    Returns path to downloaded Excel file.
    """
    if on_step:
        on_step("[Scraper] Connecting to WIPO PatentScope...")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    # Visit the browse page to get session/cookies
    resp = session.get(WIPO_BROWSE_URL, timeout=30)
    resp.raise_for_status()

    if on_step:
        on_step(f"[Scraper] Connected — status {resp.status_code}")

    # Look for Excel export link on the page
    # WIPO pages typically have an export-to-Excel button
    # The exact mechanism depends on the page structure
    excel_pattern = re.compile(r'href=["\']([^"\']*(?:xls|xlsx|csv)[^"\']*)', re.IGNORECASE)
    matches = excel_pattern.findall(resp.text)

    if matches:
        excel_url = matches[0]
        if not excel_url.startswith("http"):
            excel_url = urljoin(WIPO_BASE, excel_url)

        if on_step:
            on_step(f"[Scraper] Found Excel download link, downloading...")

        excel_resp = session.get(excel_url, timeout=60)
        excel_resp.raise_for_status()

        output_dir = Path(__file__).parent.parent.parent / "uploads"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "wipo_weekly_browse.xlsx"

        with open(output_path, "wb") as f:
            f.write(excel_resp.content)

        if on_step:
            on_step(f"[Scraper] Excel downloaded: {output_path.name} ({len(excel_resp.content)} bytes)")

        return str(output_path)

    if on_step:
        on_step("[Scraper] No direct Excel link found — page may require JS interaction")

    return None


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
