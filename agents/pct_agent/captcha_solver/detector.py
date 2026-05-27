"""Classify which captcha family is currently on the page.

Each family needs a different solving technique:
  - wipo_text:        single distorted-text image in WIPO's #psCaptchaForm
  - wipo_image_grid:  3x3 (or similar) photo grid inside #psCaptchaForm — looks
                      like reCAPTCHA but served directly by WIPO, image tags
                      are visible to the parent page (not cross-origin)
  - recaptcha_v2:     Google reCAPTCHA v2 (click-images or audio fallback)
                      served inside an iframe
  - hcaptcha:         hCaptcha challenge
  - turnstile:        Cloudflare Turnstile
  - unknown:          anything we don't recognize — falls straight to manual

Real-world data point from a captured sample: WIPO actually serves a custom
photo-grid inside #psCaptchaForm rather than the old distorted-text image.
The detector now disambiguates between the two by counting images inside.
"""

WIPO_FORM_SELECTOR = "#psCaptchaForm"
RECAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha']",
    "div.g-recaptcha",
]
HCAPTCHA_SELECTORS = [
    "iframe[src*='hcaptcha']",
    "div.h-captcha",
]
TURNSTILE_SELECTORS = [
    "iframe[src*='challenges.cloudflare.com']",
    "div.cf-turnstile",
]


def _has_visible(page, selectors):
    for selector in selectors:
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


def _wipo_form_visible(page):
    try:
        locator = page.locator(WIPO_FORM_SELECTOR)
        return locator.count() > 0 and locator.first.is_visible()
    except Exception:
        return False


def _wipo_form_image_count(page):
    """Count visible <img> tags inside #psCaptchaForm.
    1 image  → classic distorted-text captcha.
    >1 image → photo grid challenge (select-the-X).
    """
    try:
        imgs = page.locator(f"{WIPO_FORM_SELECTOR} img")
        total = imgs.count()
    except Exception:
        return 0
    visible = 0
    for idx in range(min(total, 16)):
        try:
            if imgs.nth(idx).is_visible():
                visible += 1
        except Exception:
            continue
    return visible


def classify_captcha(page):
    """Return a string identifying which family is on screen, or 'unknown'.
    Order matters — more specific markers checked first.
    """
    try:
        # Real iframe-based reCAPTCHA: most specific because the iframe URL
        # is unambiguous. Check this FIRST so we don't misclassify a real
        # reCAPTCHA that happens to be hosted inside #psCaptchaForm.
        if _has_visible(page, RECAPTCHA_SELECTORS):
            return "recaptcha_v2"
        if _has_visible(page, HCAPTCHA_SELECTORS):
            return "hcaptcha"
        if _has_visible(page, TURNSTILE_SELECTORS):
            return "turnstile"

        # WIPO's own form — disambiguate by counting inner images.
        if _wipo_form_visible(page):
            img_count = _wipo_form_image_count(page)
            if img_count >= 3:
                return "wipo_image_grid"
            return "wipo_text"
    except Exception:
        pass
    return "unknown"
