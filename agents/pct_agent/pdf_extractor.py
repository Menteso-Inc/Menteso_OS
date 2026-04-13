"""
PCT Sub-Agent: PDF Extractor
Extracts email addresses, phone numbers, and person names from PDF files.
Supports both text-based and scanned (image) PDFs via Windows OCR fallback.
"""
import re
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import winocr
    from PIL import Image
    import io
    HAS_WINOCR = True
except ImportError:
    HAS_WINOCR = False

# Regex patterns for contact info
EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE
)

PHONE_PATTERN = re.compile(
    r'(?:'
    r'\+\d{1,3}[\s\-]?\d[\s\-]?(?:\d[\s\-]?){6,14}'  # international: +61 8 6183 2900
    r'|'
    r'\(\d{2,4}\)\s?\d[\s\-]?(?:\d[\s\-]?){5,12}'     # (02) 1234 5678
    r'|'
    r'\d{7,15}'                                         # plain 7+ digit number
    r')',
)

# Patterns to find person names near keywords in patent docs
NAME_PATTERNS = [
    re.compile(r'(?:inventor|inventeur|erfinder)[:\s]+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})', re.MULTILINE),
    re.compile(r'(?:agent|attorney|representative|mandataire)[:\s]+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})', re.MULTILINE),
    re.compile(r'Name\s*\(LAST,?\s*First\)\s*([A-Z][a-zA-Z]+,?\s+[A-Z][a-zA-Z]+)', re.MULTILINE),
    re.compile(r'(?:applicant|demandeur|anmelder)[:\s]+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3})', re.MULTILINE),
]

# Filter out common false positives for phone numbers
PHONE_BLACKLIST = {
    "0000000000", "1234567890", "1111111111",
}


def extract_text_from_pdf(pdf_path, on_step=None):
    """Extract all text content from a PDF file.
    Uses direct text extraction first, then falls back to OCR for scanned PDFs.
    """
    if not HAS_PYMUPDF:
        raise ImportError("PyMuPDF (fitz) is required. Install with: pip install PyMuPDF")

    doc = fitz.open(pdf_path)
    page_count = doc.page_count

    # First try: direct text extraction
    text = ""
    for page in doc:
        text += page.get_text() + "\n"

    if len(text.strip()) > 50:
        # Got meaningful text — no OCR needed
        if on_step:
            on_step(f"[PDF Extractor] Extracted {len(text)} chars from {page_count} pages (text-based)")
        doc.close()
        return text

    # Fallback: OCR for scanned/image PDFs
    if on_step:
        on_step(f"[PDF Extractor] Scanned PDF detected — running OCR on {page_count} pages...")

    ocr_text = _ocr_pdf(doc, on_step)
    doc.close()

    if ocr_text:
        if on_step:
            on_step(f"[PDF Extractor] OCR extracted {len(ocr_text)} chars from {page_count} pages")
        return ocr_text

    if on_step:
        on_step("[PDF Extractor] OCR produced no text")
    return text  # Return whatever we got (might be empty)


def _ocr_page_worker(img_data):
    """Run OCR on a single page image. Runs in a separate thread to avoid
    event loop conflicts with Playwright."""
    img = Image.open(io.BytesIO(img_data))
    result = winocr.recognize_pil_sync(img, "en")
    return result.get("text", "")


def _ocr_pdf(doc, on_step=None):
    """OCR a PDF document using Windows OCR (winocr).
    Runs OCR in a worker thread to avoid asyncio event loop conflicts."""
    import concurrent.futures

    if not HAS_WINOCR:
        if on_step:
            on_step("[PDF Extractor] OCR not available — install winocr: pip install winocr Pillow")
        return ""

    all_text = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        for i, page in enumerate(doc):
            # Render page to image at 300 DPI for good OCR quality
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")

            try:
                future = executor.submit(_ocr_page_worker, img_data)
                page_text = future.result(timeout=60)
                all_text.append(page_text)
            except Exception as e:
                if on_step:
                    on_step(f"[PDF Extractor] OCR failed on page {i+1}: {e}")

    return "\n".join(all_text)


def find_emails(text):
    """Find all email addresses in text."""
    emails = EMAIL_PATTERN.findall(text)
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
        # Must be a real phone: 10+ digits, or starts with +
        if digits in PHONE_BLACKLIST:
            continue
        if p.strip().startswith('+') and len(digits) >= 9:
            cleaned.append(p.strip())
        elif len(digits) >= 10 and len(digits) <= 15:
            cleaned.append(p.strip())
    return list(dict.fromkeys(cleaned))


NOISE_NAMES = {"Name", "First", "Last", "Date", "Address", "Title", "Form", "Office",
               "State", "Version", "Inventor", "Applicant", "Agent", "Patent", "None",
               "Perth", "Western", "Eastern", "Northern", "Southern", "North", "South",
               "East", "West", "Street", "Road", "Avenue", "Unit", "Australia",
               "States", "International", "Filing", "Bureau", "Authority", "Petition",
               "Queensland", "Victoria", "Wales", "Zealand", "London", "Berlin", "Tokyo",
               "Yatala", "Melbourne", "Sydney", "Brisbane", "California", "York",
               # German/French form labels
               "FAMILIENNAME", "Anschrift", "Vorname", "Adresse", "Telefon", "Datum",
               "Bezeichnung", "Anmelder", "Erfinder", "Vertreter"}

def find_names(text):
    """Find person names in text near relevant keywords."""
    names = []

    # Primary: LAST, First format (supports ALL-CAPS last names like COLE, Christopher)
    last_first = re.findall(r'([A-Z][A-Za-z]{2,}),\s+([A-Z][a-zA-Z]{2,})', text)
    for last, first in last_first:
        if last not in NOISE_NAMES and first not in NOISE_NAMES:
            names.append(f"{last}, {first}")

    # Secondary: keyword-based patterns
    for pattern in NAME_PATTERNS:
        matches = pattern.findall(text)
        for m in matches:
            name = m.strip()
            words = name.split()
            if (len(words) >= 2
                    and not name.isupper()
                    and not any(w in NOISE_NAMES for w in words)):
                names.append(name)

    return list(dict.fromkeys(names))


def extract_contacts_from_pdf(pdf_path, on_step=None):
    """
    Main extraction function.
    Returns dict with emails, phones, name, and status.
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
            "name": "",
        }

    emails = find_emails(text)
    phones = find_phones(text)
    names = find_names(text)

    if on_step:
        on_step(
            f"[PDF Extractor] Found {len(emails)} email(s), "
            f"{len(phones)} phone(s), {len(names)} name(s)"
        )

    if not emails and not phones:
        return {
            "status": "not_found",
            "emails": [],
            "phones": [],
            "name": names[0] if names else "",
            "text_length": len(text),
        }

    return {
        "status": "found",
        "emails": emails,
        "phones": phones,
        "name": names[0] if names else "",
        "text_length": len(text),
    }
