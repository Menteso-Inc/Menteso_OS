"""Request pacing — Tier 0 of the captcha-prevention strategy.

Slows requests just enough to stay under the rate-limit threshold of the
target site. Adds random jitter so the request stream doesn't look robotic.
Bumps the delay temporarily after a captcha has just been solved (since that
window is when the site is most likely to challenge again).

All values are configurable via env vars (see .env.example).
"""
import random
import threading
import time

from .config import get_env


def _read_float(key, fallback):
    raw = get_env(key)
    if not raw:
        return fallback
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _read_int(key, fallback):
    raw = get_env(key)
    if not raw:
        return fallback
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


class RequestPacer:
    """Thread-safe pacer. Call .wait() before every outbound request.

    Behavior:
      - Sleeps until at least `min_delay` has passed since the previous wait()
      - Adds uniform jitter in [0, jitter] on top
      - After report_captcha() fires, the next `boost_requests` calls use a
        multiplier on the delay; multiplier decays back to 1.0 over those calls.
    """

    def __init__(
        self,
        min_delay=None,
        jitter=None,
        post_captcha_multiplier=None,
        boost_requests=5,
    ):
        self._lock = threading.Lock()
        self._last = 0.0
        # Faster defaults — captcha_solver now absorbs any captchas the
        # higher rate triggers. Override via .env if you need to throttle
        # harder (e.g. PACING_MIN_DELAY_SECONDS=0.8 for the old behavior).
        self.min_delay = (
            min_delay if min_delay is not None
            else _read_float("PACING_MIN_DELAY_SECONDS", 0.3)
        )
        self.jitter = (
            jitter if jitter is not None
            else _read_float("PACING_JITTER_SECONDS", 0.3)
        )
        self.post_captcha_multiplier = (
            post_captcha_multiplier if post_captcha_multiplier is not None
            else _read_float("PACING_POST_CAPTCHA_MULTIPLIER", 3.0)
        )
        self.boost_requests = max(0, _read_int("PACING_BOOST_REQUESTS", boost_requests))
        self._boost_remaining = 0

    def wait(self):
        """Block until the next request is allowed."""
        with self._lock:
            now = time.time()
            delay = self.min_delay + random.uniform(0, max(0.0, self.jitter))
            if self._boost_remaining > 0:
                delay *= self.post_captcha_multiplier
                self._boost_remaining -= 1
            elapsed = now - self._last
            to_sleep = max(0.0, delay - elapsed)
            self._last = now + to_sleep
        if to_sleep > 0:
            time.sleep(to_sleep)

    def report_captcha(self):
        """Tell the pacer a captcha just fired; bump delay for next N requests."""
        with self._lock:
            self._boost_remaining = self.boost_requests


# A shared default instance every agent can import. Each agent is free to
# instantiate its own if it wants different timing.
default_pacer = RequestPacer()
