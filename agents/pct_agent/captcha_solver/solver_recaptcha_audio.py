"""Audio-challenge solver for real Google reCAPTCHA v2.

reCAPTCHA renders the challenge inside a cross-origin iframe (the "bframe"
URL contains `/recaptcha/api2/bframe`). That iframe is reachable from
Playwright via `frame_locator`, so we can:

  1. Click the headphones icon → switch from image to audio challenge
  2. Grab the audio download URL from `.rc-audiochallenge-tdownload-link`
  3. Download the MP3 ourselves with `requests` (using browser cookies)
  4. Send the audio to OpenAI Whisper (cheap, very accurate on captcha audio)
  5. Type the transcribed text into the response field
  6. Click Verify

If reCAPTCHA rate-limits the audio fallback or marks us as a bot, the
verify step fails silently and we return False so the orchestrator can
escalate to manual.
"""
import time

import requests

from shared.config import get_env

OPENAI_WHISPER_ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-1"


def _api_key():
    return get_env("OPENAI_API_KEY") or ""


def _bframe(page):
    """Return the FrameLocator for the reCAPTCHA challenge iframe."""
    return page.frame_locator("iframe[src*='recaptcha/api2/bframe']")


def _switch_to_audio(bframe, step):
    try:
        btn = bframe.locator("#recaptcha-audio-button")
        btn.wait_for(state="visible", timeout=4000)
        btn.click()
        return True
    except Exception as e:
        step(f"[Solver:Audio] Could not switch to audio challenge: {e}")
        return False


def _grab_audio_url(bframe, step, max_seconds=10):
    """Find the audio download link inside the challenge iframe."""
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        try:
            link = bframe.locator(".rc-audiochallenge-tdownload-link")
            if link.count() > 0:
                href = link.first.get_attribute("href")
                if href:
                    return href
        except Exception:
            pass
        time.sleep(0.3)
    step("[Solver:Audio] Audio download link did not appear in time")
    return None


def _download_audio(page, audio_url, step):
    """Download the captcha audio using the same cookies as the browser."""
    try:
        cookies = {c["name"]: c["value"] for c in page.context.cookies()}
        ua = page.evaluate("navigator.userAgent")
        resp = requests.get(
            audio_url, cookies=cookies, headers={"User-Agent": ua}, timeout=15,
        )
        if resp.status_code != 200 or len(resp.content) < 1000:
            step(f"[Solver:Audio] Audio download returned {resp.status_code}, "
                 f"{len(resp.content)} bytes")
            return None
        return resp.content
    except Exception as e:
        step(f"[Solver:Audio] Audio download failed: {e}")
        return None


def _transcribe(audio_bytes, step, timeout=60):
    """Send audio to OpenAI Whisper and return the transcript text."""
    key = _api_key()
    if not key:
        step("[Solver:Audio] OPENAI_API_KEY not set — cannot transcribe")
        return None
    try:
        files = {"file": ("audio.mp3", audio_bytes, "audio/mpeg")}
        data = {"model": WHISPER_MODEL, "language": "en"}
        headers = {"Authorization": f"Bearer {key}"}
        resp = requests.post(
            OPENAI_WHISPER_ENDPOINT,
            files=files, data=data, headers=headers, timeout=timeout,
        )
    except Exception as e:
        step(f"[Solver:Audio] Whisper request failed: {e}")
        return None

    if resp.status_code != 200:
        step(f"[Solver:Audio] Whisper {resp.status_code}: {resp.text[:200]}")
        return None

    try:
        return (resp.json().get("text") or "").strip()
    except Exception as e:
        step(f"[Solver:Audio] Could not parse Whisper response: {e}")
        return None


def _submit_answer(bframe, answer, step):
    """Type the transcribed answer into the audio-response field and verify."""
    try:
        input_field = bframe.locator("#audio-response")
        input_field.wait_for(state="visible", timeout=4000)
        input_field.fill(answer)
    except Exception as e:
        step(f"[Solver:Audio] Could not type answer: {e}")
        return False

    try:
        verify = bframe.locator("#recaptcha-verify-button")
        verify.click()
        return True
    except Exception as e:
        step(f"[Solver:Audio] Verify click failed: {e}")
        return False


def _challenge_dismissed(page, max_seconds):
    """Poll until the reCAPTCHA challenge iframe is gone OR the anchor frame
    reports that the user is verified (checkbox shows ticked).
    """
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        try:
            bframe_count = page.locator("iframe[src*='recaptcha/api2/bframe']").count()
        except Exception:
            bframe_count = 0
        if bframe_count == 0:
            return True

        # Some sites just hide the bframe instead of removing it; check the
        # anchor's "I'm not a robot" checkbox state.
        try:
            anchor = page.frame_locator("iframe[src*='recaptcha/api2/anchor']")
            checked = anchor.locator("#recaptcha-anchor[aria-checked='true']").count()
            if checked > 0:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def solve_recaptcha_audio(page, on_step=None, max_seconds=90):
    """Solve a Google reCAPTCHA v2 by using the audio-fallback challenge.

    Returns (success, audio_bytes_or_None, transcribed_text_or_None).
    Audio bytes are returned even on failure so the sample store can
    keep them for later analysis.
    """
    step = on_step or (lambda *_a, **_k: None)

    if not _api_key():
        step("[Solver:Audio] OPENAI_API_KEY not set — skipping")
        return False, None, None

    bframe = _bframe(page)

    if not _switch_to_audio(bframe, step):
        return False, None, None

    audio_url = _grab_audio_url(bframe, step)
    if not audio_url:
        return False, None, None

    audio_bytes = _download_audio(page, audio_url, step)
    if not audio_bytes:
        return False, None, None

    step("[Solver:Audio] Audio downloaded, sending to Whisper…")
    transcript = _transcribe(audio_bytes, step, timeout=min(max_seconds, 60))
    if not transcript:
        return False, audio_bytes, None

    # Whisper returns punctuation we don't want for reCAPTCHA's strict match.
    cleaned = "".join(ch for ch in transcript if ch.isalnum() or ch == " ").strip()
    step(f"[Solver:Audio] Whisper transcript: {cleaned!r}")

    if not _submit_answer(bframe, cleaned, step):
        return False, audio_bytes, cleaned

    if _challenge_dismissed(page, max_seconds=min(max_seconds, 20)):
        step("[Solver:Audio] reCAPTCHA accepted — verified")
        return True, audio_bytes, cleaned

    step("[Solver:Audio] reCAPTCHA still showing — answer rejected")
    return False, audio_bytes, cleaned
