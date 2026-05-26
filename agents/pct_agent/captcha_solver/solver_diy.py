"""Tier 1 — In-process OCR solver for WIPO's text-image CAPTCHA.

Strategy: screenshot the captcha element, preprocess (grayscale + contrast
boost + light denoise via Pillow), run winocr on the cleaned image, sanitize
the output, type it into the answer field, click submit, wait for the form
to disappear.

winocr is Windows-only — on other platforms this tier short-circuits and the
orchestrator escalates to Tier 2 (OpenAI vision).
"""
import io
import re
import time

try:
    import winocr
    from PIL import Image, ImageOps, ImageFilter
    HAS_WINOCR = True
except ImportError:
    HAS_WINOCR = False


CAPTCHA_FORM_SELECTOR = "#psCaptchaForm"
CAPTCHA_IMAGE_SELECTORS = [
    "#psCaptchaForm img",
    "#psCaptchaForm canvas",
    "img[id*='captcha']",
    "img[src*='captcha']",
]
ANSWER_INPUT_SELECTORS = [
    "#psCaptchaForm input[type='text']",
    "#psCaptchaForm input:not([type='hidden']):not([type='submit'])",
    "input[name*='captcha']",
    "input[id*='captcha']",
]
SUBMIT_SELECTORS = [
    "#psCaptchaForm button[type='submit']",
    "#psCaptchaForm input[type='submit']",
    "#psCaptchaForm button",
]

# WIPO captcha is plain alphanumeric, usually 5-7 chars
ANSWER_CLEANUP = re.compile(r"[^A-Za-z0-9]")


def _first_visible(page, selectors):
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = locator.count()
        except Exception:
            continue
        for idx in range(min(count, 5)):
            try:
                element = locator.nth(idx)
                if element.is_visible():
                    return element
            except Exception:
                continue
    return None


def _grab_image_bytes(page):
    """Return raw PNG bytes of the captcha challenge image, or None."""
    element = _first_visible(page, CAPTCHA_IMAGE_SELECTORS)
    if not element:
        return None
    try:
        return element.screenshot(type="png")
    except Exception:
        return None


def _preprocess(image_bytes):
    """Light cleanup that empirically helps winocr on distorted text."""
    img = Image.open(io.BytesIO(image_bytes)).convert("L")  # grayscale
    img = ImageOps.autocontrast(img, cutoff=2)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    # Upscale 2x — small distorted glyphs are easier for OCR at higher DPI.
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    return img


def _ocr(image_bytes):
    if not HAS_WINOCR:
        return ""
    try:
        img = _preprocess(image_bytes)
        result = winocr.recognize_pil_sync(img, "en")
        text = (result.get("text") or "").strip()
        return ANSWER_CLEANUP.sub("", text)
    except Exception:
        return ""


def solve_wipo_text(page, on_step=None, max_seconds=30):
    """Try to read & submit the WIPO captcha.
    Returns (success_bool, image_bytes_or_None, recognized_answer_or_None).

    `image_bytes` is returned even on failure so the caller can persist the
    sample for later training.
    """
    step = on_step or (lambda *_a, **_k: None)

    if not HAS_WINOCR:
        step("[Solver:DIY] winocr not installed — skipping Tier 1")
        return False, None, None

    image_bytes = _grab_image_bytes(page)
    if not image_bytes:
        step("[Solver:DIY] Could not screenshot the captcha image")
        return False, None, None

    answer = _ocr(image_bytes)
    if not answer or len(answer) < 4:
        step(f"[Solver:DIY] OCR result too short to be valid: {answer!r}")
        return False, image_bytes, answer

    step(f"[Solver:DIY] OCR read: {answer!r}")

    input_box = _first_visible(page, ANSWER_INPUT_SELECTORS)
    if not input_box:
        step("[Solver:DIY] Answer input field not found")
        return False, image_bytes, answer

    try:
        input_box.fill("")
        input_box.fill(answer)
    except Exception as e:
        step(f"[Solver:DIY] Could not type the answer: {e}")
        return False, image_bytes, answer

    submit_btn = _first_visible(page, SUBMIT_SELECTORS)
    try:
        if submit_btn:
            submit_btn.click()
        else:
            input_box.press("Enter")
    except Exception as e:
        step(f"[Solver:DIY] Could not submit the form: {e}")
        return False, image_bytes, answer

    # Wait for the captcha form to disappear, signaling acceptance.
    # Hard-capped: form clears in 1-2s when the answer was correct; longer
    # wait just means we're burning time on a wrong OCR read.
    POST_CLICK_VERIFY_CEILING = 5
    deadline = time.time() + min(max_seconds, POST_CLICK_VERIFY_CEILING)
    while time.time() < deadline:
        try:
            form_locator = page.locator(CAPTCHA_FORM_SELECTOR)
            still_visible = form_locator.count() > 0 and form_locator.first.is_visible()
        except Exception:
            still_visible = False
        if not still_visible:
            step("[Solver:DIY] Captcha form gone — answer accepted")
            return True, image_bytes, answer
        time.sleep(0.5)

    step("[Solver:DIY] Captcha form still visible after submit — answer rejected")
    return False, image_bytes, answer
