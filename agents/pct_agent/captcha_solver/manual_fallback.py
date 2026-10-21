"""Tier 3 — Manual fallback.

This handler engages the human without any model or paid API call.

Two modes:

1. **In-place** (agent already running headed) — beep + poll the existing
   visible Chromium window until the human solves the challenge.

2. **Popup** (agent running headless) — spawn a SEPARATE headed Chromium
   window pointed at the same patent URL with the worker's cookies copied
   over so it's the same session. After the human solves it, fresh cookies
   are copied back into the headless worker, the popup is closed, and the
   headless page is reloaded so it picks up the solved-captcha session
   token.

Mode is decided by reading PCT_HEADLESS_MODE at call time — if true, popup;
otherwise, in-place.
"""
import os
import time

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

from .solver_diy import CAPTCHA_FORM_SELECTOR, CAPTCHA_IMAGE_SELECTORS, _first_visible


def _beep():
    if not HAS_WINSOUND:
        return
    try:
        winsound.MessageBeep()
    except Exception:
        pass


def _grab_screenshot(page):
    element = _first_visible(page, CAPTCHA_IMAGE_SELECTORS)
    try:
        if element:
            return element.screenshot(type="png")
        return page.screenshot(type="png", full_page=False)
    except Exception:
        return None


def _form_visible(page):
    try:
        locator = page.locator(CAPTCHA_FORM_SELECTOR)
        if locator.count() == 0:
            return False
        return locator.first.is_visible()
    except Exception:
        return False


def _is_headless_mode():
    """Same env read as agent.py uses when launching browsers."""
    return (os.getenv("PCT_HEADLESS_MODE") or "true").lower() in ("1", "true", "yes")


def _patent_page_ready(page):
    """A missing form alone also describes a blank, loading or closed page."""
    try:
        if page.is_closed() or _form_visible(page):
            return False
        from ..browser import _page_has_captcha_selectors, _title_looks_like_captcha
        if _page_has_captcha_selectors(page) or _title_looks_like_captcha(page) or '403' in page.title():
            return False
        form = page.locator('#detailMainForm')
        return bool((form.count() and form.first.is_visible())
                    or page.get_by_text('PCT Biblio', exact=False).first.is_visible())
    except Exception:
        return False


def wait_for_manual(page, on_step=None, max_seconds=300):
    """Engage the human to solve the captcha. Returns (success, image_bytes)."""
    step = on_step or (lambda *_a, **_k: None)
    image_bytes = _grab_screenshot(page)

    if _is_headless_mode():
        return _solve_via_popup(page, step, max_seconds, image_bytes)
    return _solve_in_place(page, step, max_seconds, image_bytes)


def _solve_in_place(page, step, max_seconds, image_bytes):
    """Headed-mode behavior — the user solves in the already-visible window."""
    _beep()
    step("[Solver:Manual] Manual confirmation required — solve the captcha in the browser window")
    deadline = time.time() + max_seconds
    last_beep = time.time()
    while time.time() < deadline:
        if _patent_page_ready(page):
            step("[Solver:Manual] Captcha cleared by human — resuming")
            return True, image_bytes
        if time.time() - last_beep > 30:
            _beep()
            last_beep = time.time()
        time.sleep(0.5)
    step("[Solver:Manual] Timed out waiting for the human")
    return False, image_bytes


def _solve_via_popup(page, step, max_seconds, image_bytes):
    """Headless-mode behavior — spawn a visible Chromium window, transfer
    cookies, wait for the human, transfer cookies back, close popup.
    """
    # Capture state from the headless worker.
    try:
        url = page.url
        cookies = page.context.cookies()
    except Exception as e:
        step(f"[Solver:Manual] Could not capture worker state: {e}")
        return False, image_bytes

    try:
        ua = page.evaluate("navigator.userAgent")
    except Exception:
        ua = None

    try:
        browser_type = page.context.browser.browser_type
    except Exception as e:
        step(f"[Solver:Manual] Could not access browser_type for popup: {e}")
        return False, image_bytes

    _beep()
    step("[Solver:Manual] Manual confirmation required — opening a Chromium window for you to solve")

    headed_browser = None
    headed_context = None
    headed_page = None
    try:
        headed_browser = browser_type.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        ctx_kwargs = {"viewport": {"width": 1280, "height": 800}}
        if ua:
            ctx_kwargs["user_agent"] = ua
        headed_context = headed_browser.new_context(**ctx_kwargs)
        if cookies:
            try:
                headed_context.add_cookies(cookies)
            except Exception as e:
                step(f"[Solver:Manual] Could not seed popup cookies: {e}")

        headed_page = headed_context.new_page()
        try:
            headed_page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            step(f"[Solver:Manual] Popup navigation failed: {e}")
            return False, image_bytes

        step("[Solver:Manual] Solve the captcha in the new window — it will close automatically when done")

        # Poll until the captcha form is gone in the headed popup OR timeout.
        deadline = time.time() + max_seconds
        last_beep = time.time()
        solved = False
        while time.time() < deadline:
            if _patent_page_ready(headed_page):
                solved = True
                step("[Solver:Manual] Captcha cleared in the popup — transferring session")
                break
            if time.time() - last_beep > 30:
                _beep()
                last_beep = time.time()
            time.sleep(0.5)

        if not solved:
            step("[Solver:Manual] Timed out waiting for the human")
            return False, image_bytes

        # Copy refreshed cookies back into the worker's headless context.
        try:
            fresh = headed_context.cookies()
            if fresh:
                page.context.add_cookies(fresh)
        except Exception as e:
            step(f"[Solver:Manual] Could not transfer cookies back: {e}")
            return False, image_bytes

        # Reload the headless page so it re-fetches with the new session.
        try:
            page.reload(wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            step(f"[Solver:Manual] Reload after popup failed (will retry on next poll): {e}")

        # Confirm the actual worker can read the patent after the transfer.
        # Do not count a cleared popup as a solved challenge on another page.
        confirm_deadline = time.monotonic() + 15
        while time.monotonic() < confirm_deadline:
            if _patent_page_ready(page):
                step("[Solver:Manual] Patent page confirmed in worker — resuming")
                return True, image_bytes
            time.sleep(0.5)
        step("[Solver:Manual] Worker page not confirmed after manual session transfer")
        return False, image_bytes
    finally:
        # ALWAYS close the popup, even on errors. This is the user's
        # explicit ask: "close that chromium window even after solve".
        try:
            if headed_page:
                headed_page.close()
        except Exception:
            pass
        try:
            if headed_context:
                headed_context.close()
        except Exception:
            pass
        try:
            if headed_browser:
                headed_browser.close()
        except Exception:
            pass
