"""Cross-pipeline coordinator for the PCT agent.

Why this exists:
  When ChunkedPipelineManager runs N parallel PipelinePCT instances at L5,
  each pipeline used to keep its OWN contact cache and its OWN captcha
  cooldown. Two real problems:
    1. Same applicant scraped N times across pipelines (wasted work).
    2. When pipeline A hit a captcha and started cooling, pipelines B/C/D
       kept hammering WIPO and triggered more captchas, compounding the
       block instead of relieving it.

  This module replaces those per-pipeline objects with shared singletons so
  every parallel pipeline sees the same cache and the same captcha state.
"""
import threading
import time


class SharedContactCache:
    """Thread-safe applicant -> contacts cache, shared across pipelines."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache = {}

    def get(self, applicant):
        key = self._normalize(applicant)
        if not key:
            return None
        with self._lock:
            return self._cache.get(key)

    def put(self, applicant, contacts):
        key = self._normalize(applicant)
        if not key or (contacts or {}).get("status") != "found":
            return
        if not contacts.get("emails"):
            return
        with self._lock:
            self._cache[key] = {
                "emails": contacts["emails"],
                "phones": contacts["phones"],
                "name": contacts.get("name", ""),
                "status": "found",
            }

    @staticmethod
    def _normalize(applicant):
        if not applicant:
            return None
        s = applicant.strip().lower()
        for suffix in (" gmbh", " ag", " pty ltd", " ltd", " inc", " co"):
            s = s.replace(suffix, "")
        s = s.strip()
        return s if len(s) > 3 else None


class SharedCaptchaCoordinator:
    """Global captcha cooldown — any worker hitting a captcha pauses ALL
    parallel pipelines, not just its own. Stops the cascade where one
    pipeline gets challenged and the others escalate the block.
    """

    def __init__(self, on_step=None):
        self._lock = threading.Lock()
        self._cooldown_until = 0.0
        self._consecutive = 0
        self._step = on_step or (lambda m: None)

    def report_captcha(self):
        with self._lock:
            self._consecutive += 1
            backoff = min(15 * (2 ** (self._consecutive - 1)), 90)
            self._cooldown_until = time.time() + backoff
            self._step(
                f"[Coordinator] CAPTCHA — all pipelines pausing {backoff}s "
                f"(global hit #{self._consecutive})"
            )

    def report_clear(self):
        with self._lock:
            if self._consecutive > 0:
                self._consecutive = max(0, self._consecutive - 1)

    def wait_if_cooling(self):
        while True:
            with self._lock:
                remaining = self._cooldown_until - time.time()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 1))

    def cooldown_remaining(self):
        with self._lock:
            return max(0, self._cooldown_until - time.time())

    @property
    def state(self):
        return "cooldown" if self.cooldown_remaining() > 0 else "ok"
