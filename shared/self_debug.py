import traceback


def diagnose_error(error_info):
    """Analyze an error and suggest a fix using pattern matching."""
    error = error_info.get("error", "")
    tb = error_info.get("traceback", "")

    if "401" in error or "403" in error or "Unauthorized" in error:
        return {"diagnosis": "API authentication error", "fix": "Check API key in .env"}
    if "429" in error or "rate limit" in error.lower():
        return {"diagnosis": "Rate limit hit", "fix": "Wait and retry with backoff"}
    if "timeout" in error.lower() or "timed out" in error.lower():
        return {"diagnosis": "Request timeout", "fix": "Retry with longer timeout"}
    if "KeyError" in error or "KeyError" in tb:
        return {"diagnosis": "Missing data field", "fix": "Check input data structure"}
    if "FileNotFoundError" in error or "FileNotFoundError" in tb:
        return {"diagnosis": "File not found", "fix": "Check file path exists"}
    if "ConnectionError" in error or "ConnectionError" in tb:
        return {"diagnosis": "Network connection failed", "fix": "Check network and retry"}
    if "JSONDecodeError" in error or "JSONDecodeError" in tb:
        return {"diagnosis": "Invalid JSON response", "fix": "Check API response format"}

    return {"diagnosis": "Unknown error", "fix": "Review full traceback for details"}


def run_with_self_debug(run_fn, max_retries=3, on_step=None):
    """
    Execute a function with self-debugging.
    On failure: diagnoses error, logs it, retries.
    After max_retries: returns structured failure.
    """
    errors = []

    for attempt in range(1, max_retries + 1):
        try:
            if on_step:
                on_step(f"Attempt {attempt}/{max_retries}...")
            result = run_fn()
            return {"status": "success", "result": result, "attempts": attempt}
        except Exception as e:
            error_info = {
                "attempt": attempt,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
            errors.append(error_info)
            diagnosis = diagnose_error(error_info)

            if on_step:
                on_step(
                    f"[Attempt {attempt} failed] {diagnosis['diagnosis']} — {diagnosis['fix']}"
                )

    return {"status": "failure", "errors": errors, "attempts": max_retries}
