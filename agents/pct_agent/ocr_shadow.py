"""Offline speed experiment; never used to authorize production output.

Two OCR engines can agree on an error. A confidence score is not a measured
accuracy probability. Emails always remain on the independent vision path.
"""
from __future__ import annotations

import threading
import time

_ENGINE = None
_LOCK = threading.Lock()


def recognize_line(image):
    """Recognize one known line without repeating page detection/classification."""
    global _ENGINE
    from rapidocr import RapidOCR
    started = time.monotonic()
    with _LOCK:
        if _ENGINE is None:
            _ENGINE = RapidOCR(params={
                'Global.log_level': 'error',
                'EngineConfig.onnxruntime.intra_op_num_threads': 1,
                'EngineConfig.onnxruntime.inter_op_num_threads': 1,
            })
        result = _ENGINE(image, use_det=False, use_cls=False, use_rec=True)
    texts = list(result.txts or [])
    scores = list(result.scores) if result.scores is not None else []
    return {'text': texts[0] if len(texts) == 1 else '',
            'score': float(scores[0]) if len(scores) == 1 else 0.0,
            'seconds': round(time.monotonic() - started, 4)}


def candidate(kind, source_lines, source_engine, reading, threshold=0.99):
    """Conservative *shadow* candidate, not permission to skip verification."""
    from . import contact_policy as policy
    if kind not in {'name', 'phone'}:
        return False
    if source_engine != 'windows_en' or len(source_lines) != 1:
        return False  # Never count the same OCR model twice as independent.
    if reading.get('score', 0) < threshold:
        return False
    original = source_lines[0]['text'].strip()
    other = reading.get('text', '').strip()
    return bool(original and other and policy.value_key(kind, original) == policy.value_key(kind, other))
