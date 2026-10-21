"""Retired paid CAPTCHA adapter; compatibility entry point makes no API calls."""


def solve_via_openai_vision(page, captcha_type, on_step=None, max_seconds=60):
    if on_step:
        on_step("[Solver] Paid CAPTCHA adapter disabled; manual confirmation required")
    return False, None, None
