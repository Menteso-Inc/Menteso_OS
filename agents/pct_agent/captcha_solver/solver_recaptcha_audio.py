"""Retired paid CAPTCHA adapter; compatibility entry point makes no API calls."""


def solve_recaptcha_audio(page, on_step=None, max_seconds=90):
    if on_step:
        on_step("[Solver] Paid CAPTCHA adapter disabled; manual confirmation required")
    return False, None, None
