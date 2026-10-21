"""CAPTCHA Solver — internal sub-agent of the PCT agent.

Lives under `agents/pct_agent/captcha_solver/` rather than as a top-level
agent because only the PCT browser pipeline calls into it today. It is
*not* exposed as its own card on the dashboard — its status surfaces via
the PCT agent's run log.

CAPTCHA handling requires manual confirmation. No model API is used.

Public API:
    solve_captcha(page, on_step=None, max_seconds=None) -> bool
        Called by pct_agent.browser. Returns True when the captcha resolved.

    run_agent(input_data=None, on_step=None) -> dict
        Standalone diagnostic — opens its own browser against a test URL.
        Invoke via:  python -m agents.pct_agent.captcha_solver.agent
"""
import time
from datetime import datetime, timezone

from shared.config import get_env
from shared.memory import load_memory, save_learning

from .detector import classify_captcha
from .manual_fallback import wait_for_manual
from .sample_store import save_sample
from .tests import tests


# Memory path: agents/pct_agent/captcha_solver/memory.json
# shared.memory accepts a slash-separated agent_name and resolves it relative
# to AGENTS_DIR via pathlib, so this works without touching shared/memory.py.
AGENT_NAME = "pct_agent/captcha_solver"

def _enabled_tiers(captcha_type):
    """Legacy configuration must not silently re-enable paid API calls."""
    return ("manual",)


def _max_seconds(override=None):
    if override is not None:
        return int(override)
    raw = get_env("CAPTCHA_SOLVER_MAX_SECONDS")
    try:
        return int(raw) if raw else 120
    except (TypeError, ValueError):
        return 120


def _emit(on_step, message, event=None, **extra):
    """Send both a plain-text line and a structured browser event so the
    existing dashboard handler picks the right tier badge up.
    """
    if not on_step:
        return
    try:
        on_step(message)
    except Exception:
        pass
    if event:
        payload = {
            "type": "browser",
            "event": event,
            "message": message,
            **extra,
        }
        try:
            on_step(payload)
        except Exception:
            pass


def _run_tier(tier, page, captcha_type, on_step, deadline):
    """Manual confirmation only. Returns (success, image_bytes, answer)."""
    remaining = max(0, int(deadline - time.time()))
    if remaining <= 0:
        return False, None, None

    if tier == "manual":
        success, image_bytes = wait_for_manual(
            page, on_step=on_step, max_seconds=remaining,
        )
        return success, image_bytes, None

    _emit(on_step, f"[Solver] Automatic tier '{tier}' is disabled; manual confirmation required")
    return False, None, None


def solve_captcha(page, on_step=None, max_seconds=None, source_url=""):
    """Resolve a captcha on the given Playwright page.

    Requests manual confirmation and records the outcome for diagnostics.
    Old automatic-tier environment settings cannot enable a model call.

    Returns True if the challenge was cleared, False otherwise.
    """
    start = time.time()
    max_seconds = _max_seconds(max_seconds)
    deadline = start + max_seconds
    captcha_type = classify_captcha(page)
    tiers = _enabled_tiers(captcha_type)

    attempts = []
    final_outcome = "failed"
    final_tier = ""
    final_answer = ""
    final_image = None
    # Track the most informative answer/attempt we saw, even on failure, so
    # the saved sample sidecar tells us what each tier tried.
    last_answer_attempt = ""

    _emit(
        on_step,
        f"[Solver] Captcha detected (type={captcha_type}) — trying tiers: {','.join(tiers)}",
        event="captcha_detected",
        captcha_active=True,
        captcha_type=captcha_type,
    )

    try:
        for tier in tiers:
            if time.time() >= deadline:
                attempts.append({"tier": tier, "result": "skipped_timeout"})
                break

            _emit(
                on_step,
                f"[Solver] Attempting tier '{tier}'",
                event="solver_attempt",
                tier=tier,
                captcha_type=captcha_type,
            )

            # Each tier is wrapped — an exception inside a tier becomes a
            # logged failure on that tier, not a crash that loses everything.
            try:
                success, image_bytes, answer = _run_tier(
                    tier, page, captcha_type, on_step, deadline,
                )
            except Exception as tier_exc:
                _emit(on_step, f"[Solver] Tier '{tier}' crashed: {tier_exc}")
                success, image_bytes, answer = False, None, None
                attempts.append({
                    "tier": tier, "result": "crashed", "error": str(tier_exc)[:200],
                })
                continue

            if image_bytes and not final_image:
                final_image = image_bytes

            if answer:
                last_answer_attempt = answer

            attempts.append({
                "tier": tier,
                "result": "solved" if success else "failed",
                "answer": answer or "",
            })

            if success:
                final_outcome = "manual_solved" if tier == "manual" else "solved"
                final_tier = tier
                final_answer = answer or ""
                _emit(
                    on_step,
                    f"[Solver] Cleared captcha via tier '{tier}'",
                    event="solver_succeeded",
                    tier=tier,
                    captcha_type=captcha_type,
                    confirmed=tier == "manual",
                )
                _emit(
                    on_step,
                    "CAPTCHA cleared - resuming from the same row",
                    event="captcha_cleared",
                    captcha_active=False,
                )
                break

            _emit(
                on_step,
                f"[Solver] Tier '{tier}' failed — escalating",
                event="solver_failed_escalating",
                tier=tier,
                captcha_type=captcha_type,
            )

        if final_outcome == "failed":
            # Failure is distinct from clearance; do not show a success banner.
            _emit(
                on_step,
                "[Solver] All tiers exhausted — giving up on this captcha",
                event="captcha_failed",
                captcha_active=False,
            )

        return final_outcome in {"solved", "manual_solved"}
    finally:
        # ALWAYS persist whatever we collected, even on exception. This is
        # the user's "save the data on failure" guarantee.
        if final_image is not None:
            try:
                # Persist the best answer we have: a successful answer wins;
                # otherwise the last attempted answer (so the sidecar shows
                # what each tier guessed even when none of them won).
                recorded_answer = final_answer or last_answer_attempt
                save_sample(
                    image_bytes=final_image,
                    answer=recorded_answer,
                    tier_used=final_tier or "none",
                    captcha_type=captcha_type,
                    url=source_url,
                    attempts=attempts,
                )
            except Exception:
                pass

        elapsed = time.time() - start
        insight = (
            f"captcha_type={captcha_type} outcome={final_outcome} "
            f"tier={final_tier or 'none'} elapsed={elapsed:.1f}s "
            f"attempts={len(attempts)}"
        )
        try:
            save_learning(
                AGENT_NAME, "solve_captcha", final_outcome, insight,
                strategy=(final_tier or "none"), execution_time=elapsed,
            )
        except Exception:
            pass


def run_agent(input_data=None, on_step=None):
    """Standalone diagnostic entry point. Opens a Playwright browser against
    `target_url` (default: WIPO PatentScope home, which is harmless if no
    captcha is currently triggered) and exercises the solve loop end-to-end.
    """
    start = time.time()
    input_data = input_data or {}
    target_url = input_data.get("target_url") or "https://patentscope.wipo.int/search/en/structuredSearch.jsf"
    max_seconds = _max_seconds(input_data.get("max_seconds"))

    step = on_step or (lambda *_a, **_k: None)

    step(f"[Solver:Diagnostic] Loading {target_url}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _fail("Playwright not installed", start)

    memory = load_memory(AGENT_NAME)
    step(
        f"[Solver:Diagnostic] Memory loaded — {memory['stats']['total_runs']} past runs, "
        f"{memory['stats']['success_rate']:.0%} success rate"
    )

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            except Exception as e:
                browser.close()
                return _fail(f"Could not load target URL: {e}", start)

            from .detector import classify_captcha as _classify
            detected = _classify(page)
            step(f"[Solver:Diagnostic] Classifier result: {detected}")

            if detected == "unknown":
                browser.close()
                return {
                    "status": "success",
                    "outcome": "no_captcha_present",
                    "tier_used": "none",
                    "captcha_type": detected,
                    "elapsed_seconds": round(time.time() - start, 2),
                    "max_seconds": max_seconds,
                    "attempts": [{"tier": "n/a", "result": "no_captcha"}],
                    "tests": tests.run({
                        "outcome": "skipped",
                        "tier_used": "none",
                        "captcha_type": detected,
                        "elapsed_seconds": time.time() - start,
                        "max_seconds": max_seconds,
                        "attempts": [{"tier": "n/a", "result": "no_captcha"}],
                    }),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            result = solve_captcha(
                page, on_step=on_step, max_seconds=max_seconds, source_url=target_url,
            )
            browser.close()

            elapsed = time.time() - start
            outcome = "solved" if result else "failed"
            payload = {
                "outcome": outcome,
                "tier_used": "manual",
                "captcha_type": detected,
                "elapsed_seconds": elapsed,
                "max_seconds": max_seconds,
                "attempts": [{"tier": "orchestrated", "result": outcome}],
            }
            return {
                "status": "success" if result else "partial",
                **payload,
                "tests": tests.run(payload),
                "execution_time": round(elapsed, 2),
                "attempts_log": payload["attempts"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        return _fail(f"Diagnostic crashed: {e}", start)


def _fail(error_msg, start):
    return {
        "status": "failure",
        "error": error_msg,
        "outcome": "error",
        "tier_used": "none",
        "captcha_type": "",
        "elapsed_seconds": round(time.time() - start, 2),
        "max_seconds": _max_seconds(None),
        "attempts": [],
        "tests": {"passed": False, "total": 0, "passed_count": 0, "failed_count": 0, "failures": []},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    def _print(msg):
        print(msg if isinstance(msg, str) else f"[event] {msg}")
    result = run_agent(on_step=_print)
    print("---")
    print(result)
