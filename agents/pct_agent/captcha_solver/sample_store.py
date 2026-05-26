"""Sample collection — every captcha image we see is saved to disk along
with the eventual answer and metadata. Builds a free training set so we can
later replace the paid OpenAI tier with a local model.

Layout:
    logs/pct_agent/captcha_solver/samples/YYYY-MM-DD/
        <uuid>.png    — raw cropped image
        <uuid>.json   — { "answer": "...", "tier_used": "...", "captcha_type": "...",
                          "timestamp": "...", "url": "..." }
"""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from shared.config import get_env

# This file lives at agents/pct_agent/captcha_solver/sample_store.py so the
# project root is four levels up.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLES_ROOT = PROJECT_ROOT / "logs" / "pct_agent" / "captcha_solver" / "samples"

_write_lock = threading.Lock()


def _enabled():
    return (get_env("CAPTCHA_SOLVER_SAVE_SAMPLES") or "true").lower() not in (
        "0", "false", "no",
    )


def save_sample(image_bytes, answer, tier_used, captcha_type, url="", attempts=None):
    """Persist a captcha sample. Returns the saved image path or None.

    Best-effort — any error is swallowed so a save failure can never block
    a real solve. `image_bytes` may be None when the tier doesn't actually
    capture an image (e.g. manual fallback on a non-image challenge); in
    that case only the metadata sidecar is written.

    `attempts` is an optional list of per-tier attempt dicts:
        [{"tier": "diy", "result": "failed", "answer": "..."}, ...]
    Saving this makes the sidecar a debugging breadcrumb — you can read it
    after a failed solve and see exactly what each tier guessed.
    """
    if not _enabled():
        return None
    try:
        date_dir = SAMPLES_ROOT / datetime.now().strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        sample_id = uuid.uuid4().hex[:12]
        png_path = date_dir / f"{sample_id}.png"
        json_path = date_dir / f"{sample_id}.json"

        with _write_lock:
            if image_bytes:
                with open(png_path, "wb") as f:
                    f.write(image_bytes)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({
                    "id": sample_id,
                    "answer": answer or "",
                    "tier_used": tier_used or "",
                    "captcha_type": captcha_type or "",
                    "url": url or "",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "has_image": bool(image_bytes),
                    "attempts": attempts or [],
                }, f, indent=2)

        return str(png_path if image_bytes else json_path)
    except Exception:
        return None
