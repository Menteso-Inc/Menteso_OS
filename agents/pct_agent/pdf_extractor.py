"""
PCT Sub-Agent: PDF Extractor
Extracts email addresses and phone numbers from PDF files.
"""
import re
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# Regex patterns for contact info
EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE
)

PHONE_PATTERN = re.compile(
    r'(?:'
    r'(?:\+\d{1,3}[\s\-]?)?'             # optional country code
    r'(?:\(?\d{1,4}\)?[\s\-]?)?'          # optional area code
    r'(?:\d[\s\-]?){6,14}\d'              # main number
    r')',
    re.IGNORECASE
)

# Filter out common false positives for phone numbers
PHONE_BLACKLIST = {
    "0000000000", "1234567890", "1111111111",
}


def extract_text_from_pdf(pdf_path, on_step=None):
    """Extract all text content from a PDF file."""
    if not HAS_PYMUPDF:
        if on_step:
            on_step("[PDF Extractor] PyMuPDF not installed — install with: pip install PyMuPDF")
        raise ImportError("PyMuPDF (fitz) is required. Install with: pip install PyMuPDF")

    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page_num, page in enumerate(doc):
            page_text = page.get_text()
            text += page_text + "\n"
        doc.close()

        if on_step:
            on_step(f"[PDF Extractor] Extracted {len(text)} chars from {doc.page_count} pages")

    except Exception as e:
        if on_step:
            on_step(f"[PDF Extractor] Error reading PDF: {e}")
        raise

    return text


def find_emails(text):
    """Find all email addresses in text."""
    emails = EMAIL_PATTERN.findall(text)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for e in emails:
        lower = e.lower()
        if lower not in seen:
            seen.add(lower)
            unique.append(e)
    return unique


def find_phones(text):
    """Find all phone numbers in text."""
    raw_phones = PHONE_PATTERN.findall(text)
    cleaned = []
    for p in raw_phones:
        digits = re.sub(r'[^\d]', '', p)
        if len(digits) >= 7 and digits not in PHONE_BLACKLIST:
            cleaned.append(p.strip())
    # Deduplicate
    return list(dict.fromkeys(cleaned))


def extract_contacts_from_pdf(pdf_path, on_step=None):
    """
    Main extraction function.
    Returns dict with emails, phones, and status.
    """
    if on_step:
        on_step(f"[PDF Extractor] Processing: {pdf_path}")

    try:
        text = extract_text_from_pdf(pdf_path, on_step)
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "emails": [],
            "phones": [],
        }

    emails = find_emails(text)
    phones = find_phones(text)

    if on_step:
        on_step(f"[PDF Extractor] Found {len(emails)} email(s), {len(phones)} phone(s)")

    if not emails and not phones:
        return {
            "status": "not_found",
            "emails": [],
            "phones": [],
            "text_length": len(text),
        }

    return {
        "status": "found",
        "emails": emails,
        "phones": phones,
        "text_length": len(text),
    }
