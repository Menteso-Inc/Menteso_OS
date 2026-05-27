"""Universal vision-based solver — Tier 2.

Strategy: take a screenshot of the captcha region (the whole #psCaptchaForm
or the page viewport if we can't locate the form), send it to GPT-4o vision
with a structured-output prompt asking the model to identify what kind of
challenge it is and what to do. Then act on the response:

  - text-input:  type the answer into the field, submit
  - click-tiles: click each indicated tile, then click verify
  - unknown:     return failure, orchestrator escalates to manual

This replaces the original text-only Tier 2. The reason: a real WIPO captcha
sample turned out to be a 3x3 photo grid ("select images with X"), not the
old distorted-text image. The new solver handles both shapes uniformly.
"""
import base64
import io
import json
import re
import time

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import requests

from shared.config import get_env

from .solver_diy import (
    ANSWER_INPUT_SELECTORS,
    CAPTCHA_FORM_SELECTOR,
    SUBMIT_SELECTORS,
    _first_visible,
)

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o"
ANSWER_CLEANUP = re.compile(r"[^A-Za-z0-9]")

PROMPT_UNIVERSAL = """You are looking at a CAPTCHA challenge served by the WIPO patent website.
Identify what the user is being asked to do and reply with ONLY a JSON object
(no prose, no markdown fences) shaped exactly like this:

{
  "kind": "text" | "click_tiles" | "unknown",
  "instruction": "<short text of the instruction shown to the user>",
  "answer": "<the characters to type, only when kind=text. Use uppercase letters and digits. Empty string otherwise>",
  "tiles_to_click": [<1-based tile indices counted left-to-right then top-to-bottom>]
}

Rules:
- If the challenge is distorted text that should be typed, set kind=text and put the characters in answer.
- If the challenge is a grid of photos and the user must click certain ones, set kind=click_tiles and list the tile numbers (1-9 for a 3x3 grid, 1-16 for a 4x4 grid). Number left-to-right then top-to-bottom.
- If you cannot tell, set kind=unknown and leave the other fields empty.
- Reply with the JSON object alone. No explanation."""


def _api_key():
    return get_env("OPENAI_API_KEY") or ""


def _model():
    return get_env("CAPTCHA_SOLVER_OPENAI_MODEL") or DEFAULT_MODEL


def _captcha_region_screenshot(page):
    """Screenshot the whole captcha region. Prefers the WIPO form element so
    the LLM sees instruction + tiles together; falls back to viewport.
    """
    try:
        locator = page.locator(CAPTCHA_FORM_SELECTOR)
        if locator.count() > 0 and locator.first.is_visible():
            return locator.first.screenshot(type="png")
    except Exception:
        pass
    try:
        return page.screenshot(type="png", full_page=False)
    except Exception:
        return None


def _post_to_openai(image_bytes, prompt, timeout=60):
    key = _api_key()
    if not key:
        return None, "OPENAI_API_KEY not configured"

    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": _model(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 200,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            OPENAI_ENDPOINT, json=payload, headers=headers, timeout=timeout,
        )
    except Exception as e:
        return None, f"HTTP error: {e}"

    if resp.status_code != 200:
        return None, f"OpenAI {resp.status_code}: {resp.text[:200]}"

    try:
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return None, f"Could not parse response: {e}"
    return text, None


def _extract_json(raw):
    """Pull the first {...} JSON object out of GPT's response — tolerant to
    code fences or stray text the model might add despite the prompt."""
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*({.*?})\s*```", raw, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    else:
        brace = re.search(r"({.*})", raw, re.DOTALL)
        candidate = brace.group(1) if brace else raw
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _submit_text(page, answer, on_step):
    step = on_step or (lambda *_a, **_k: None)
    input_box = _first_visible(page, ANSWER_INPUT_SELECTORS)
    if not input_box:
        step("[Solver:Vision] No text input field found")
        return False
    try:
        input_box.fill("")
        input_box.fill(answer)
    except Exception as e:
        step(f"[Solver:Vision] Could not type answer: {e}")
        return False
    submit_btn = _first_visible(page, SUBMIT_SELECTORS)
    try:
        if submit_btn:
            submit_btn.click()
        else:
            input_box.press("Enter")
        return True
    except Exception as e:
        step(f"[Solver:Vision] Could not submit: {e}")
        return False


def _click_tiles(page, tile_indices, on_step):
    """Click the numbered tiles inside #psCaptchaForm, then click submit.
    Tiles are numbered 1-N reading left-to-right then top-to-bottom.
    """
    step = on_step or (lambda *_a, **_k: None)
    try:
        tiles = page.locator(f"{CAPTCHA_FORM_SELECTOR} img")
        total = tiles.count()
    except Exception as e:
        step(f"[Solver:Vision] Could not enumerate tiles: {e}")
        return False

    if total == 0:
        step("[Solver:Vision] No tile images found inside captcha form")
        return False

    clicked_any = False
    for one_based in tile_indices:
        try:
            idx = int(one_based) - 1
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= total:
            step(f"[Solver:Vision] Tile index {one_based} out of range (1..{total})")
            continue
        try:
            tiles.nth(idx).click()
            clicked_any = True
        except Exception as e:
            step(f"[Solver:Vision] Tile {one_based} click failed: {e}")

    if not clicked_any:
        return False

    # WIPO's image-grid captcha is click-only — picking the right tile clears
    # the form immediately, no separate submit. Give it a beat and check:
    # if the form is already gone, we've won and don't need a submit button.
    try:
        page.wait_for_timeout(800)
    except Exception:
        pass
    try:
        form = page.locator(CAPTCHA_FORM_SELECTOR)
        if form.count() == 0 or not form.first.is_visible():
            step("[Solver:Vision] Tile click cleared the form — no submit needed")
            return True
    except Exception:
        pass

    # Form still up: this implementation needs an explicit submit. Try it.
    submit_btn = _first_visible(page, SUBMIT_SELECTORS)
    if not submit_btn:
        step("[Solver:Vision] No submit button visible — assuming click-only flow")
        # Don't fail. Let the caller's _wait_for_form_gone decide; if WIPO
        # accepts the tile click asynchronously we'll see the form disappear.
        return True
    try:
        submit_btn.click()
        return True
    except Exception as e:
        step(f"[Solver:Vision] Submit click failed: {e}")
        return False


def _wait_for_form_gone(page, max_seconds):
    """Poll until #psCaptchaForm disappears (server accepted the answer).

    Hard-capped to a short wait: when the click was correct the form is
    gone in 1-2 seconds. A longer wait just means we burned time on a
    wrong answer that the orchestrator should escalate to the next tier.
    """
    POST_CLICK_VERIFY_CEILING = 5  # seconds
    deadline = time.time() + min(max_seconds, POST_CLICK_VERIFY_CEILING)
    while time.time() < deadline:
        try:
            form = page.locator(CAPTCHA_FORM_SELECTOR)
            visible = form.count() > 0 and form.first.is_visible()
        except Exception:
            visible = False
        if not visible:
            return True
        time.sleep(0.25)
    return False


def solve_via_openai_vision(page, captcha_type, on_step=None, max_seconds=60):
    """Universal vision solver. Returns (success, image_bytes, answer_or_summary)."""
    step = on_step or (lambda *_a, **_k: None)

    if not _api_key():
        step("[Solver:Vision] OPENAI_API_KEY missing — skipping Tier 2")
        return False, None, None

    # Real Google reCAPTCHA renders inside a cross-origin iframe — we can't
    # screenshot or click inside it from the parent page. Bail to the
    # dedicated audio-challenge solver / manual fallback.
    if captcha_type in {"recaptcha_v2", "hcaptcha", "turnstile"}:
        step(f"[Solver:Vision] {captcha_type} is iframe-isolated — escalating")
        return False, None, None

    image_bytes = _captcha_region_screenshot(page)
    if not image_bytes:
        step("[Solver:Vision] Could not screenshot the challenge")
        return False, None, None

    step("[Solver:Vision] Sending challenge image to GPT-4o…")
    raw, error = _post_to_openai(image_bytes, PROMPT_UNIVERSAL, timeout=min(max_seconds, 60))
    if error:
        step(f"[Solver:Vision] {error}")
        return False, image_bytes, None

    parsed = _extract_json(raw)
    if not parsed:
        step(f"[Solver:Vision] Could not parse JSON from response: {raw[:200]!r}")
        return False, image_bytes, raw[:100]

    kind = (parsed.get("kind") or "").lower()
    instruction = parsed.get("instruction") or ""
    step(f"[Solver:Vision] kind={kind} instruction={instruction!r}")

    if kind == "text":
        answer = ANSWER_CLEANUP.sub("", parsed.get("answer") or "")
        if len(answer) < 3:
            step(f"[Solver:Vision] text answer too short: {answer!r}")
            return False, image_bytes, answer
        if not _submit_text(page, answer, on_step):
            return False, image_bytes, answer
        success = _wait_for_form_gone(page, max_seconds)
        return success, image_bytes, answer

    if kind == "click_tiles":
        tiles = parsed.get("tiles_to_click") or []
        if not tiles:
            step("[Solver:Vision] Model returned click_tiles with empty list")
            return False, image_bytes, "tiles:[]"
        step(f"[Solver:Vision] Clicking tiles: {tiles}")
        if not _click_tiles(page, tiles, on_step):
            return False, image_bytes, f"tiles:{tiles}"
        success = _wait_for_form_gone(page, max_seconds)
        return success, image_bytes, f"tiles:{tiles}"

    step("[Solver:Vision] kind=unknown — escalating")
    return False, image_bytes, None
