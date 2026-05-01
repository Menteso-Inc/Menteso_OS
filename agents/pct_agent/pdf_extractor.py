"""
PCT Sub-Agent: PDF Extractor
Extracts email addresses, phone numbers, and person names from PDF files.
Smart OCR: prioritises page 2 (contact page), early exit on email found.
"""
import re
import threading
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

# ---------------------------------------------------------------------------
# Email regex — primary + OCR-artifact tolerant
# ---------------------------------------------------------------------------
EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE
)

# Phone regex
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


# ---------------------------------------------------------------------------
# OCR artifact cleanup — critical for email recovery
# ---------------------------------------------------------------------------
def _is_valid_email(email):
    """Validate that an extracted email is plausible (filters OCR overruns).
    When we strip spaces from OCR text, the regex can overshoot and capture
    trailing words like 'office@sonn.atGmbHco'.  The TLD check catches this.
    """
    parts = email.rsplit('.', 1)
    if len(parts) != 2:
        return False
    tld = parts[1]
    # TLD should be 2-6 letters only (com, at, org, co, uk, info, etc.)
    if not (2 <= len(tld) <= 6 and tld.isalpha()):
        return False
    # Local part should have at least 1 char
    local = email.split('@')[0]
    if len(local) < 1:
        return False
    return True


def _extract_emails_around_at(text):
    """Reconstruct OCR-damaged emails by finding @ tokens and expanding.
    OCR commonly produces:  "offi ce@ wi rnsberger-lerchbaum. com"
    Split into words: ["offi", "ce@", "wi", "rnsberger-lerchbaum.", "com"]

    Algorithm:
      1. Find each word containing @
      2. Expand RIGHT one word at a time until the domain has a valid TLD
         (stop at the MINIMUM right expansion — avoids grabbing extra words)
      3. Expand LEFT to capture the full local part (maximise left expansion)
    """
    words = text.split()
    emails = []
    used = set()

    for idx, word in enumerate(words):
        if '@' not in word or idx in used:
            continue

        # Step 1: Find minimum right expansion that gives a valid domain TLD
        right_end = None
        for right in range(min(8, len(words) - idx)):
            end = idx + right + 1
            joined = ''.join(words[idx:end])
            if '@' in joined:
                domain_part = joined.split('@', 1)[1]
                if '.' in domain_part:
                    tld = domain_part.rsplit('.', 1)[1]
                    if 2 <= len(tld) <= 6 and tld.isalpha():
                        right_end = end
                        break

        if right_end is None:
            continue

        # Step 2: Expand left — but only if local part looks incomplete
        at_pos_in_word = word.index('@')
        local_so_far = word[:at_pos_in_word]  # e.g. "ce" from "ce@"

        # Start with no left expansion
        joined = ''.join(words[idx:right_end])
        matches = [m for m in EMAIL_PATTERN.findall(joined) if _is_valid_email(m)]
        best_email = matches[0] if matches else None

        # Only expand left if the local part is very short (OCR likely split it)
        if len(local_so_far) <= 3:
            for left in range(1, min(4, idx + 1)):
                prev_word = words[idx - left]
                # Stop if the previous word isn't purely alphabetic
                # (digits, symbols, phone numbers are not part of an email)
                if not prev_word.isalpha():
                    break
                start = idx - left
                joined = ''.join(words[start:right_end])
                matches = [m for m in EMAIL_PATTERN.findall(joined) if _is_valid_email(m)]
                if matches:
                    best_email = max(matches, key=len)
                    # Stop expanding once local part is a reasonable length
                    local_part = best_email.split('@')[0]
                    if len(local_part) >= 4:
                        break

        if best_email:
            emails.append(best_email)
            for j in range(max(0, idx - 3), right_end):
                used.add(j)

    return emails


# ---------------------------------------------------------------------------
# Smart text extraction — prioritise contact pages, early exit on email found
# ---------------------------------------------------------------------------

# Reusable OCR thread executor (avoid creating per-page)
_ocr_executor = None
_ocr_executor_lock = threading.Lock()


def _get_ocr_executor():
    global _ocr_executor
    if _ocr_executor is None:
        with _ocr_executor_lock:
            if _ocr_executor is None:
                import concurrent.futures
                _ocr_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    return _ocr_executor


def extract_text_from_pdf(pdf_path, on_step=None):
    """Smart extraction: prioritise page 2 (contact page in RO/101 forms).
    1. Text-extract all pages (fast, <50ms)
    2. If email found in text → done
    3. OCR page 2 first (contact page) → check for email
    4. OCR remaining pages only if still no email
    """
    if not HAS_PYMUPDF:
        raise ImportError("PyMuPDF (fitz) is required. Install with: pip install PyMuPDF")

    doc = fitz.open(pdf_path)
    page_count = doc.page_count

    # Pass 1: Fast text extraction on all pages
    texts = []
    for page in doc:
        texts.append(page.get_text())

    combined = "\n".join(texts)

    # Quick email check on extracted text
    if '@' in combined and find_emails(combined):
        doc.close()
        return combined

    # Pass 2: OCR priority pages (page 2 first, then page 1, then rest)
    if not HAS_WINOCR:
        doc.close()
        return combined

    # Order: page 2 (index 1) → page 1 (index 0) → page 3+ → only first 5 pages max
    priority_order = []
    if page_count > 1:
        priority_order.append(1)  # Page 2 — contacts in RO/101
    priority_order.append(0)      # Page 1
    for i in range(2, min(page_count, 5)):
        priority_order.append(i)

    ocr_texts = list(texts)  # copy
    for i in priority_order:
        page = doc[i]
        # Only OCR if text was sparse on this page
        if len(texts[i].strip()) < 30:
            ocr_result = _ocr_single_page(page, i)
            if ocr_result:
                ocr_texts[i] = ocr_result

            # Check if we found an email after this page
            partial = "\n".join(ocr_texts)
            if '@' in partial and find_emails(partial):
                doc.close()
                return partial

    doc.close()
    return "\n".join(ocr_texts)


def _ocr_single_page(page, page_index, on_step=None):
    """OCR a single PDF page at 200 DPI (fast).  Returns text or empty."""
    if not HAS_WINOCR:
        return ""

    try:
        # 200 DPI for speed (was 300) — still good enough for email extraction
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")

        executor = _get_ocr_executor()
        future = executor.submit(_ocr_page_worker, img_data)
        return future.result(timeout=30)
    except Exception:
        return ""


def _ocr_page_worker(img_data):
    """Run OCR on a single page image."""
    img = Image.open(io.BytesIO(img_data))
    result = winocr.recognize_pil_sync(img, "en")
    return result.get("text", "")


# ---------------------------------------------------------------------------
# Contact finders
# ---------------------------------------------------------------------------
def find_emails(text):
    """Find all email addresses in text, including OCR-damaged ones.
    Uses two strategies:
      1. Standard regex on raw text (works for clean text-based PDFs)
      2. Window-around-@ with space stripping + validation (handles OCR
         artefacts like "offi ce@ wi rnsberger-lerchbaum. com")
    """
    emails = []

    # Strategy 1: Standard regex on raw text
    for e in EMAIL_PATTERN.findall(text):
        if _is_valid_email(e):
            emails.append(e)

    # Strategy 2: Find every @, grab surrounding window, strip spaces, match
    emails += _extract_emails_around_at(text)

    # Deduplicate, case-insensitive
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


# ---------------------------------------------------------------------------
# Main extraction — multi-pass with OCR retry
# ---------------------------------------------------------------------------
def extract_contacts_from_pdf(pdf_path, on_step=None):
    """Main extraction function.
    Smart extraction already handles text + targeted OCR with early exit.
    No redundant full-OCR retry needed.
    """
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
