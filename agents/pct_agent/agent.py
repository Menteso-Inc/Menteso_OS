"""
PCT Agent — Patent Cooperation Treaty
Reads WIPO resultList.xls → scrapes patent pages → extracts contacts → outputs Work Report Excel.

Input:  resultList.xls (from WIPO PatentScope weekly browse) or .xlsx with same columns
Output: Work Report DD-Month-YYYY.xlsx matching the standard work report format
"""
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import openpyxl
    from openpyxl.styles import Font
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

try:
    import xlrd
    HAS_XLRD = True
except ImportError:
    HAS_XLRD = False

from shared.memory import load_memory, save_learning, get_best_strategy
from shared.self_debug import run_with_self_debug
from .scraper import download_wipo_excel
from .browser import PatentBrowser, BrowserStopRequested
from .pdf_extractor import extract_contacts_from_pdf
from .ai_verifier import validate_configuration, result_metadata, enabled as ai_enabled
from .pipeline import ChunkedPipelineManager, ProgressFile, RESULT_STATUS_PRIORITY
from .tests import tests

# Pipeline config
# Lowered threshold so even small runs benefit from chunked processing.
PIPELINE_THRESHOLD = 20
DEFAULT_CHUNK_SIZE = 500
# Short cooldown between chunks (was 1.5s) — captcha solver handles bursts.
CHUNK_COOLDOWN_SECONDS = 0.3

# Parallel pipeline worker counts. Conservative defaults to keep WIPO happy:
# 4 simultaneous browsers is enough for ~50-150 rows/min, low enough that
# WIPO rarely rate-limits a single home IP. Push higher only if you have
# IP rotation (Tor or paid proxies).
DEFAULT_BROWSER_WORKERS = 4
DEFAULT_DOWNLOAD_WORKERS = 6
DEFAULT_OCR_WORKERS = 3
PCT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs" / "pct-work-sheets"
PCT_INPUT_ARCHIVE_DIR = PCT_OUTPUT_DIR / "input-sheets"
PCT_REPORT_EXTENSIONS = {".xlsx", ".csv", ".jsonl"}

# Fast-mode level table. Each level maps to a runtime profile.
# Level 1 is the safe sequential baseline; level 5 maxes out
# parallelism. Worker counts in the fast-mode levels are TOTAL across
# all parallel pipelines — ChunkedPipelineManager divides them down per
# chunk pipeline at construction time.
# All levels run HEADLESS. The captcha solver handles DIY OCR + GPT-4o
# Vision in the headless worker silently — no Chromium window appears.
# Only when both auto-tiers fail does manual_fallback open a SEPARATE
# visible popup Chromium for the human to solve, which closes itself
# the moment the captcha clears.
FAST_MODE_LEVELS = {
    1: {"marker": "L1", "label": "Safe",       "fast": False, "pipelines": 1, "browsers": 1, "downloads": 1,  "ocr": 1, "headless": True},
    2: {"marker": "L2", "label": "Mild",       "fast": True,  "pipelines": 1, "browsers": 2, "downloads": 3,  "ocr": 2, "headless": True},
    3: {"marker": "L3", "label": "Balanced",   "fast": True,  "pipelines": 2, "browsers": 4, "downloads": 6,  "ocr": 3, "headless": True},
    4: {"marker": "L4", "label": "Aggressive", "fast": True,  "pipelines": 3, "browsers": 6, "downloads": 9,  "ocr": 4, "headless": True},
    5: {"marker": "L5", "label": "Max",        "fast": True,  "pipelines": 4, "browsers": 8, "downloads": 12, "ocr": 6, "headless": True},
}
# Locked to L1 Safe — single-browser sequential mode. L2+ runs multiple
# Playwright tabs in parallel which WIPO firewalls at the TCP level (every
# row comes back nav_failed). One browser making one request at a time
# looks like a normal user to WIPO and actually delivers data. Throughput
# is ~6-12 rows/min; user explicitly accepted that tradeoff.
FAST_MODE_DEFAULT_LEVEL = 1


def _resolve_headless(fast_profile):
    """Decide headless mode for this run.
    Precedence: explicit PCT_HEADLESS_MODE env var (true/false) > profile.headless.
    """
    env_raw = (os.getenv("PCT_HEADLESS_MODE") or "").strip().lower()
    if env_raw in ("1", "true", "yes"):
        return True
    if env_raw in ("0", "false", "no"):
        return False
    if isinstance(fast_profile, dict):
        return fast_profile.get("headless", True)
    return True


def resolve_fast_level(input_data):
    """Always return L1 Safe.

    Even L3 (2 pipelines x 4 browsers = 8 concurrent tabs) trips WIPO's
    connection refusal at the TCP layer — every row fails with
    nav_failed before WIPO even serves a page. L1 is the only level
    that uses a SINGLE browser (fast=False, routes to
    _run_chunked_sequential_mode), which WIPO accepts. Throughput is
    ~6-12 rows/min; reliability beats throughput when the alternative
    is zero rows delivered. Inputs/env vars are ignored.
    """
    _ = input_data  # kept for signature compatibility
    return 1, FAST_MODE_LEVELS[1]

AGENT_CONFIG = {
    "name": "PCT Agent",
    "description": (
        "Patent Cooperation Treaty agent. Reads WIPO resultList Excel, "
        "scrapes PatentScope patent pages, downloads RO/101 or 306 PDFs, "
        "extracts email/phone/name contacts, and outputs a Work Report Excel."
    ),
    "role": "Patent Data Processor",
    "goal": "Extract contact information from WIPO patent filings",
    "status": "active",
    "version": "2.0.0",
    "requires_llm": False,
    "accepts_upload": True,
    "upload_types": [".xlsx", ".xls"],
    "input_fields": [
        {
            "name": "mode",
            "type": "select",
            "label": "Input Mode",
            "options": ["Upload Excel", "Download from WIPO"],
        },
    ],
    "sub_agents": ["Scraper", "PDF Extractor", "CAPTCHA Solver"],
}

# Decorative pause between major lifecycle steps. Set to 0 in production for
# maximum throughput; bump to ~0.3 if you want a more visible step-by-step
# log for demos.
STEP_DELAY = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def id_to_url(patent_id):
    """Convert patent ID to WIPO PatentScope URL.
    e.g. 'WO/2025/097187' → 'https://patentscope.wipo.int/search/en/WO2025097187'
    """
    clean = patent_id.replace("/", "")
    return f"https://patentscope.wipo.int/search/en/{clean}"


def extract_country(appl_no):
    """Extract country code from application number.
    e.g. 'US2023/078371' → 'US', 'AT2024/060361' → 'AT'
    """
    match = re.match(r'^([A-Z]{2})', str(appl_no).strip())
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# Excel reader — supports both .xls (xlrd) and .xlsx (openpyxl)
# ---------------------------------------------------------------------------
def read_input_excel(file_path, on_step=None):
    """Read WIPO resultList Excel. Returns list of row dicts.
    Handles:
      - .xls files (xlrd) — WIPO default download format
      - .xlsx files (openpyxl)
      - Skips blank rows and gazette header rows
    """
    ext = Path(file_path).suffix.lower()

    if ext == ".xls":
        if not HAS_XLRD:
            raise ImportError("xlrd is required for .xls files — pip install xlrd")
        return _read_xls(file_path, on_step)
    elif ext in (".xlsx", ".xlsm"):
        if not HAS_OPENPYXL:
            raise ImportError("openpyxl is required for .xlsx files — pip install openpyxl")
        return _read_xlsx(file_path, on_step)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def _header_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _map_columns(headers):
    """Match source columns by name; never use positional guesses for the applicant."""
    aliases = {
        "id": "id", "publicationno": "id", "publicationnumber": "id",
        "title": "title", "applicant": "applicant", "applicantname": "applicant",
        "applno": "appl_no", "applicationno": "appl_no", "applicationnumber": "appl_no",
        "kind": "kind", "ipc": "ipc", "url": "url", "researcher": "researcher",
        "priortydate": "priority_date", "prioritydate": "priority_date",
    }
    return {aliases[_header_key(h)]: i for i, h in enumerate(headers) if _header_key(h) in aliases}


def _parse_source_rows(values, on_step=None):
    header_index = None
    col_map = {}
    for index, row in enumerate(values[:10]):
        candidate = _map_columns(row)
        if "id" in candidate and "title" in candidate:
            header_index, col_map = index, candidate
            break
    required = {"id", "title", "appl_no", "applicant"}
    if header_index is None or not required.issubset(col_map):
        raise ValueError("Input must contain publication ID, Title, Application No and Applicant columns")
    rows = []
    for cells in values[header_index + 1:]:
        def value(key):
            index = col_map.get(key)
            if index is None or index >= len(cells) or cells[index] is None:
                return ""
            return str(cells[index]).strip()
        patent_id = value("id")
        if not patent_id or not re.fullmatch(r"WO/?\d{4}/?\d+", patent_id, re.I):
            continue
        rows.append({key: value(key) for key in
                     ("id", "title", "appl_no", "applicant", "kind", "ipc", "url", "researcher", "priority_date")})
    if on_step:
        on_step(f"[Excel Reader] Parsed {len(rows)} patent entries using named source columns")
    return rows


def _read_xls(file_path, on_step=None):
    wb = xlrd.open_workbook(file_path)
    try:
        ws = wb.sheet_by_index(0)
        return _parse_source_rows([ws.row_values(r) for r in range(ws.nrows)], on_step)
    finally:
        wb.release_resources()


def _read_xlsx(file_path, on_step=None):
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    try:
        return _parse_source_rows(list(wb.active.iter_rows(values_only=True)), on_step)
    finally:
        wb.close()


def _stop_requested(input_data):
    checker = (input_data or {}).get("stop_requested")
    if callable(checker):
        return checker
    return lambda: False


def _register_stop_handler(input_data, handler):
    registrar = (input_data or {}).get("register_stop_handler")
    if callable(registrar) and callable(handler):
        registrar(handler)


def _build_partial_result(status, results, total, found_count, not_found_count,
                          error_count, output_path="", execution_time=0, tests_result=None,
                          not_found_path=""):
    return {
        "status": status,
        "results": results,
        "summary": {
            "total": total,
            "processed": len(results),
            "found": found_count,
            "not_found": not_found_count,
            "errors": error_count,
        },
        "output_file": output_path,
        "not_found_file": not_found_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "execution_time": round(execution_time, 2),
        "attempts": 1,
        "tests": tests_result or {},
    }


def _archive_pct_input_sheet(file_path, on_step=None):
    source = Path(str(file_path or "")).resolve()
    if not source.exists():
        return ""
    PCT_INPUT_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.stem).strip("._") or "pct_input"
    target = (PCT_INPUT_ARCHIVE_DIR / f"{stamp}_{safe_stem}{source.suffix.lower()}").resolve()
    if PCT_INPUT_ARCHIVE_DIR.resolve() in source.parents:
        return str(source)
    shutil.copy2(str(source), str(target))
    if on_step:
        on_step(f"[Input] Archived source sheet locally: {target.name}")
    return str(target)


# ---------------------------------------------------------------------------
# Main agent runner
# ---------------------------------------------------------------------------
def run_agent(input_data=None, on_step=None):
    """
    Execute the PCT agent.
    input_data expects:
      - file_path: path to uploaded Excel (.xls or .xlsx)
      - mode: "upload" or "wipo_download"
    """
    start_time = time.time()
    agent_name = "pct_agent"
    try:
        validate_configuration(check_api=True)
    except (ValueError, OSError) as exc:
        detail = str(exc) if str(exc).startswith("openai_http_") else "Check the OpenAI key, connection and contact rules"
        return _failure(f"PCT AI verification is unavailable: {detail}")

    def step(msg):
        if on_step:
            on_step(msg)

    def browser_event(event_data):
        if on_step:
            on_step({"type": "browser", **event_data})

    # --- Step 1: Load memory ---
    step("Loading PCT agent memory...")
    time.sleep(STEP_DELAY)
    memory = load_memory(agent_name)
    runs = memory["stats"]["total_runs"]
    rate = memory["stats"]["success_rate"]
    step(f"Memory loaded — {runs} past runs, {rate:.0%} success rate")
    time.sleep(STEP_DELAY)

    # --- Step 2: Select strategy ---
    step("Selecting best strategy...")
    strategy = get_best_strategy(agent_name, "process_excel", default="sequential_scrape")
    step(f"Strategy: {strategy}")
    time.sleep(STEP_DELAY)

    # --- Step 3: Validate input ---
    if not input_data:
        input_data = {}

    mode = input_data.get("mode", "upload")
    file_path = input_data.get("file_path")
    gazette = input_data.get("gazette")
    stop_requested = _stop_requested(input_data)

    if mode == "wipo_download":
        gazette_msg = f" for week {gazette}" if gazette else ""
        step(f"[Mode: WIPO Download] Downloading Excel from PatentScope{gazette_msg}...")
        time.sleep(STEP_DELAY)

        def do_download():
            return download_wipo_excel(gazette=gazette, on_step=on_step)

        dl_result = run_with_self_debug(do_download, max_retries=2, on_step=on_step)
        if dl_result["status"] == "success" and dl_result["result"]:
            file_path = dl_result["result"]
            step(f"Excel downloaded: {file_path}")
        else:
            step("[WIPO Download] Could not download Excel — check network/URL")
            save_learning(agent_name, "process_excel", "failure",
                          "WIPO download failed", "try_different_headers")
            return _failure("Could not download Excel from WIPO PatentScope")

    if not file_path or not os.path.exists(file_path):
        step(f"ERROR: Excel file not found: {file_path}")
        return _failure(f"Excel file not found: {file_path}")

    archived_input_path = _archive_pct_input_sheet(file_path, on_step=step)

    # --- Step 4: Read input Excel ---
    step(f"[Excel Reader] Opening: {Path(file_path).name}")
    time.sleep(STEP_DELAY)

    try:
        patent_rows = read_input_excel(file_path, on_step=step)
    except Exception as e:
        step(f"ERROR: Failed to read Excel: {e}")
        return _failure(f"Failed to read Excel: {e}")

    if not patent_rows:
        step("ERROR: No patent entries found in the Excel file")
        return _failure("No patent entries found in the Excel file")

    step(f"Ready to process {len(patent_rows)} patent entries")
    time.sleep(STEP_DELAY)

    if stop_requested():
        step("Stop requested before processing started")
        return _build_partial_result("stopped", [], len(patent_rows), 0, 0, 0)

    # One WIPO browser for every sheet size. Downloading overlaps verification;
    # the legacy multi-browser fast mode is never selected or upgraded live.
    _, profile = resolve_fast_level(input_data)
    resumed_results = []
    if input_data.get("resume_path"):
        from .resume import load_handoff
        try:
            resumed_results = load_handoff(input_data["resume_path"], file_path, patent_rows)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            return _failure(f"Cannot resume safely: {exc}")
    return _run_chunked_sequential_mode(
        patent_rows, file_path, agent_name, strategy, start_time, step,
        browser_event, stop_requested,
        (input_data or {}).get("register_stop_handler"), fast_profile=profile,
        archived_input_path=archived_input_path, mode=mode, gazette=gazette,
        resumed_results=resumed_results,
    )



def _run_pipeline_mode(patent_rows, file_path, agent_name, strategy,
                       start_time, step, browser_event, stop_requested=lambda: False,
                       register_stop_handler=None, fast_profile=None,
                       live_level_getter=None, archived_input_path="", mode="", gazette=""):
    """Run the parallel pipeline for 50+ rows.  No artificial delays."""
    profile = fast_profile or FAST_MODE_LEVELS[3]
    browser_workers = profile["browsers"]
    download_workers = profile["downloads"]
    ocr_workers = profile["ocr"]
    parallel_pipelines = profile["pipelines"]

    step(f"[Pipeline] Large dataset ({len(patent_rows)} rows) — parallel pipeline mode")
    step(
        f"[Pipeline] {browser_workers} browsers + {download_workers} downloaders + "
        f"{ocr_workers} OCR across {parallel_pipelines} pipeline(s)"
    )

    # Check for resume
    resume_path = ProgressFile.find_latest(file_path)
    if resume_path:
        completed = ProgressFile.load_completed(resume_path)
        step(f"[Pipeline] Resuming — {len(completed)}/{len(patent_rows)} already done")
    else:
        resume_path = None

    # Honor profile's headless setting; PCT_HEADLESS_MODE env can override.
    headless_mode = _resolve_headless(profile)

    # Pool warm-up: re-use the pacer's "boost after captcha" mechanism to
    # slow down the first ~5 requests right after pool launch. This avoids
    # smashing WIPO with a burst of N parallel requests immediately after a
    # level upgrade (L1 → L5), which the site reads as a bot signature
    # and reacts to by serving empty/throttled pages — leading to a wave
    # of false not_found results.
    try:
        from shared.pacing import default_pacer as _pacer
        if _pacer is not None and browser_workers >= 2:
            _pacer.report_captcha()  # trips the post-captcha multiplier
            step(
                f"[Pipeline] Warm-up: throttling the first ~{_pacer.boost_requests} "
                f"requests so WIPO sees a gradual ramp, not a burst"
            )
    except Exception:
        pass

    # Build and run pipeline. Wrap in try/except so even if the parallel
    # pipeline dies catastrophically we still write whatever rows finished.
    pipeline = ChunkedPipelineManager(
        patent_rows=patent_rows,
        on_step=step,
        browser_workers=browser_workers,
        download_workers=download_workers,
        ocr_workers=ocr_workers,
        parallel_pipelines=parallel_pipelines,
        headless=headless_mode,
        resume_path=resume_path,
        input_file=file_path,
        live_level_getter=live_level_getter,
    )

    results = []
    pipeline_error = None
    try:
        results = pipeline.run()
    except Exception as e:
        pipeline_error = e
        step(f"[Pipeline] ERROR during run: {e} — saving whatever we have")

    # Retry pass: rows that came back not_found because of a SYSTEM failure
    # (WIPO throttling, captcha, timeout, download failure) are worth a
    # second attempt at lower concurrency. Rows where the page loaded fine
    # but the document genuinely has no RO/101/306/Request-form PDF are NOT
    # retried — that won't change.
    if results and not stop_requested():
        results = _retry_system_failures(
            results=results,
            patent_rows=patent_rows,
            file_path=file_path,
            on_step=step,
            stop_requested=stop_requested,
            max_iterations=int(os.getenv("PCT_RETRY_MAX_ITERATIONS", "2")),
        )

    # Generate the two deliverables from whatever rows survived.
    output_path = ""
    not_found_path = ""
    if results:
        step("Generating worked + not-found Excel reports...")
        try:
            output_path, not_found_path = write_pct_reports(results, on_step=step, gazette=gazette)
            step(f"Output saved: {Path(output_path).name} + {Path(not_found_path).name}")
        except Exception as e:
            step(f"[Output] Could not write reports: {e} — "
                 f"{len(results)} rows are in the JSONL log")
    else:
        step("No rows processed — reports not generated")

    # Self-tests
    step("Running self-tests...")
    found_count = sum(1 for r in results if r["status"] == "found")
    not_found_count = sum(1 for r in results if r["status"] == "not_found")
    error_count = sum(1 for r in results if r["status"] not in ("found", "not_found"))
    total = len(patent_rows)

    agent_result = {
        "status": "success",
        "results": results,
        "summary": {
            "total": total,
            "processed": len(results),
            "found": found_count,
            "not_found": not_found_count,
            "errors": error_count,
        },
        "output_file": output_path,
        "not_found_file": not_found_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    test_result = tests.run(agent_result)
    agent_result["tests"] = test_result

    if test_result["passed"]:
        step(f"All {test_result['total']} self-tests passed!")
    else:
        step(f"Self-tests: {test_result['passed_count']}/{test_result['total']} passed")

    # Save learning
    execution_time = time.time() - start_time
    insight = (
        f"Pipeline processed {total} rows: {found_count} contacts found, "
        f"{not_found_count} not found, {error_count} errors"
    )
    save_learning(agent_name, "process_excel", "success" if found_count > 0 else "partial",
                  insight, strategy, execution_time)

    step(f"Learning saved. Total time: {execution_time:.1f}s")
    step(f"DONE — {found_count} contacts found, {not_found_count} not found, "
         f"{error_count} errors out of {total} rows")

    agent_result["execution_time"] = round(execution_time, 2)
    agent_result["attempts"] = 1
    agent_result["input_file"] = archived_input_path or str(file_path)
    agent_result["input_file_name"] = Path(archived_input_path or file_path).name
    agent_result["mode"] = mode
    agent_result["gazette"] = gazette or ""
    return agent_result


# ---------------------------------------------------------------------------
# Retry pass — re-scrape rows that failed due to SYSTEM issues, not genuine
# missing documents. Runs after the main pipeline, with smaller concurrency
# so WIPO has a chance to recover.
# ---------------------------------------------------------------------------

# Reasons that indicate WIPO/network failure (worth retrying) rather than a
# genuinely missing document (not worth retrying).
SYSTEM_FAIL_REASONS = {
    "throttled",
    "load_timeout",
    "nav_failed",
    "docs_tab",
    "captcha",
    "captcha_persistent",
    "download_failed",
    "exception",
}


def _classify_result_for_retry(result):
    """Return True if this result should be retried.
    Genuine no_pdf_row results are skipped: re-scraping won't change them.
    """
    status = result.get("status", "")
    if status == "found":
        return False
    reason = (result.get("reason") or "").lower()
    # Error rows with no captured reason are also worth one retry.
    if status == "error" and not reason:
        return True
    if status == "error" and "scrape_exception" in reason:
        return True
    if status == "not_found":
        # Compare against the structured reason codes the browser emits.
        for marker in SYSTEM_FAIL_REASONS:
            if marker in reason:
                return True
        return False
    return False


def _retry_system_failures(results, patent_rows, file_path, on_step,
                            stop_requested, max_iterations=2):
    """Re-scrape the subset of `results` flagged as system failures.
    Loops up to `max_iterations` times, each time with progressively lower
    concurrency. Merges the recovered rows back into `results` keyed by row
    number so the final Excel stays aligned.
    """
    step = on_step or (lambda m: None)
    rows_by_id = {row.get("id"): row for row in patent_rows if row.get("id")}

    # Each retry pass uses a smaller worker count than the previous. The
    # original main run was L5 (4 pipelines x 8 browsers); retries start
    # at L2/L3 territory so WIPO sees a gentler request stream.
    retry_profiles = [
        {"pipelines": 2, "browsers": 4, "downloads": 6, "ocr": 3, "headless": True},
        {"pipelines": 1, "browsers": 2, "downloads": 3, "ocr": 2, "headless": True},
    ]

    for iteration in range(max_iterations):
        if stop_requested():
            step("[Retry] Stop requested — skipping further retry iterations")
            break

        # Gather rows still flagged as system failures
        to_retry = []
        for r in results:
            if not _classify_result_for_retry(r):
                continue
            patent_id = r.get("patent_id")
            row = rows_by_id.get(patent_id)
            if row:
                # Make sure _row_idx survives the round-trip so merge works
                row = dict(row)
                row["_row_idx"] = r.get("row", 0)
                to_retry.append(row)

        if not to_retry:
            step("[Retry] No system-failure rows remaining — done")
            return results

        profile_idx = min(iteration, len(retry_profiles) - 1)
        profile = retry_profiles[profile_idx]
        step(
            f"[Retry {iteration + 1}/{max_iterations}] Re-scraping "
            f"{len(to_retry)} system-failure row(s) at reduced concurrency "
            f"(pipelines={profile['pipelines']}, browsers={profile['browsers']})"
        )

        try:
            retry_pipeline = ChunkedPipelineManager(
                patent_rows=to_retry,
                on_step=step,
                browser_workers=profile["browsers"],
                download_workers=profile["downloads"],
                ocr_workers=profile["ocr"],
                parallel_pipelines=profile["pipelines"],
                headless=_resolve_headless(profile),
                resume_path=None,
                input_file=f"{file_path}::retry{iteration + 1}",
            )
            retry_results = retry_pipeline.run()
        except Exception as e:
            step(f"[Retry {iteration + 1}] Pipeline crashed: {e} — keeping prior results")
            break

        # Merge retry results back into the master list, keyed by row number.
        # Only upgrade a row if the retry produced a strictly better outcome
        # (found > not_found > error), so a retry that comes back not_found
        # never overwrites a previously-found result.
        merged_by_row = {r.get("row"): r for r in results if r.get("row") is not None}
        upgraded = 0
        for new_r in retry_results:
            row_no = new_r.get("row")
            if row_no is None:
                continue
            old = merged_by_row.get(row_no)
            if not old:
                merged_by_row[row_no] = new_r
                upgraded += 1
                continue
            old_score = RESULT_STATUS_PRIORITY.get(old.get("status"), 0)
            new_score = RESULT_STATUS_PRIORITY.get(new_r.get("status"), 0)
            if new_score > old_score:
                merged_by_row[row_no] = new_r
                upgraded += 1

        results = [merged_by_row[k] for k in sorted(merged_by_row)]
        step(
            f"[Retry {iteration + 1}/{max_iterations}] Recovered "
            f"{upgraded} row(s) on this pass"
        )

        if upgraded == 0:
            # Two consecutive no-progress passes would just hammer WIPO. Bail.
            step("[Retry] No progress this iteration — stopping retry loop")
            break

    return results


# ---------------------------------------------------------------------------
# Output generator — Work Report format
# ---------------------------------------------------------------------------
def _run_chunked_sequential_mode(patent_rows, file_path, agent_name, strategy,
                                 start_time, step, browser_event, stop_requested=lambda: False,
                                 register_stop_handler=None, fast_profile=None,
                                 live_level_getter=None, archived_input_path="", mode="", gazette="",
                                 resumed_results=None):
    """One browser, bounded PDF queue, concurrent independent AI readings.

    Retain the callable name for compatibility, but ignore legacy speed changes:
    they must not introduce extra WIPO browsers during this workflow.
    """
    from uuid import uuid4
    from .overlap import process_rows, RowJournal, bounded_setting

    total = len(patent_rows)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    journal = RowJournal(PCT_OUTPUT_DIR / f"pct_progress_{run_id}.jsonl", file_path, total)
    results = list(resumed_results or [])
    completed_rows = {result["row"] for result in results}
    resumed_count = len(results)
    timing_started = time.time() * 1000
    completed_at = []
    for result in results:
        journal.append(result)
    report_paths = None
    report_error = ""
    fatal_error = ""
    interval = bounded_setting("PCT_PIPELINE_MIN_ROW_INTERVAL_SECONDS", 10.0, 1.0, 60.0)
    verification_workers = bounded_setting("PCT_PDF_VERIFICATION_WORKERS", 1, 1, 4, int)
    api_concurrency = bounded_setting("PCT_PDF_API_CONCURRENCY", 8, 2, 8, int)
    pending_limit = max(verification_workers,
                        bounded_setting("PCT_PIPELINE_PENDING_PDFS", 2, 1, 8, int))

    def save_reports():
        nonlocal report_paths, report_error
        if not results:
            return
        try:
            report_paths = write_pct_reports(
                sorted(results, key=lambda result: result["row"]), on_step=step,
                gazette=gazette, output_paths=report_paths,
            )
            report_error = ""
        except Exception as exc:
            report_error = type(exc).__name__
            step(f"[Output] Sheet update failed ({report_error}); every result is saved in {journal.path.name}")

    def record(result):
        journal.append(result)
        results.append(result)
        completed_at.append(time.time() * 1000)
        del completed_at[:-20]
        if len(results) % 25 == 0:
            save_reports()

    def make_result(row, url, contacts):
        country = "" if ai_enabled() else extract_country(row["appl_no"])
        result = _row_result(
            row["_row_idx"], row, url, country, contacts.get("status", "error"),
            emails=contacts.get("emails", []), phones=contacts.get("phones", []),
            name=contacts.get("name", ""),
            reason=contacts.get("error") or contacts.get("reason", ""),
        )
        result.update(result_metadata(contacts))
        return result

    def timed_browser_event(event):
        browser_event({**event, "timing": {"startedAt": timing_started,
                       "resumedRows": resumed_count, "rowTimestamps": list(completed_at)}})

    if resumed_count:
        next_row = next((index for index in range(1, total + 1) if index not in completed_rows), total + 1)
        step(f"[Resume] Retained {resumed_count} completed rows; next unfinished row {next_row}/{total}")
        found = sum(result["status"] == "found" for result in results)
        missing = sum(result["status"] == "not_found" for result in results)
        step({"type": "pipeline_stats", "total": total, "found": found,
              "not_found": missing, "errors": resumed_count - found - missing})
        save_reports()
    timed_browser_event({"event": "pipeline", "total": total})

    step(f"[Pipeline] {total} rows: one WIPO browser, {verification_workers} PDF verification worker(s), up to {pending_limit} pending PDFs, two independent AI readings per PDF")
    if verification_workers > 1:
        step(f"[Pipeline] Isolated PDF processes; at most {api_concurrency} concurrent AI requests; all accuracy checks retained")
    step(f"[Pipeline] Minimum {interval:g}s between patent lookups; automatic backoff on failed lookups")
    browser = PatentBrowser(headless=_resolve_headless(fast_profile), on_step=step,
                            stop_requested=stop_requested)
    if callable(register_stop_handler):
        register_stop_handler(browser.force_stop)
    try:
        browser.start()
        process_rows(
            patent_rows, browser, extract_contacts_from_pdf, make_result, record,
            step, timed_browser_event, stop_requested, run_id,
            max_pending=pending_limit, min_interval=interval,
            completed_rows=completed_rows,
            verification_workers=verification_workers, api_concurrency=api_concurrency,
        )
    except BrowserStopRequested:
        step("[Pipeline] Stopped; saving completed rows")
    except Exception as exc:
        fatal_error = type(exc).__name__
        step(f"[Pipeline] Interrupted by {fatal_error}; saving completed rows")
    finally:
        browser.close()

    results.sort(key=lambda result: result["row"])
    save_reports()
    found_count = sum(result["status"] == "found" for result in results)
    not_found_count = sum(result["status"] == "not_found" for result in results)
    error_count = len(results) - found_count - not_found_count
    run_status = "stopped" if stop_requested() else "success"
    if run_status != "stopped" and (fatal_error or report_error or len(results) != total):
        run_status = "partial" if results else "failure"
    output_path, not_found_path = report_paths or ("", "")
    execution_time = time.time() - start_time
    agent_result = _build_partial_result(
        run_status, results, total, found_count, not_found_count, error_count,
        output_path=output_path, not_found_path=not_found_path, execution_time=execution_time,
    )
    agent_result["progress_file"] = str(journal.path)
    agent_result["resumed_rows"] = resumed_count
    if fatal_error or report_error:
        agent_result["error"] = fatal_error or f"report_write_failed: {report_error}"
    test_result = tests.run(agent_result)
    agent_result["tests"] = test_result
    if not test_result["passed"] and run_status == "success":
        agent_result["status"] = run_status = "partial"
    save_learning(agent_name, "process_excel", run_status,
                  f"Single-browser overlap processed {len(results)}/{total} rows: "
                  f"{found_count} found, {not_found_count} not found, {error_count} errors",
                  strategy, execution_time)
    agent_result.update(input_file=archived_input_path or str(file_path),
                        input_file_name=Path(archived_input_path or file_path).name,
                        mode=mode, gazette=gazette or "")
    step(f"[Pipeline] {run_status}: {len(results)}/{total} processed; {found_count} found, "
         f"{not_found_count} not found, {error_count} errors")
    return agent_result



WORK_REPORT_HEADERS = [
    "Publication No", "Title", "Application No.", "Applicant",
    "Url", "Cat", "Phone No.", "Email", "Agent Name", "Country",
    "Researcher", "Priorty Date",
]


def write_pct_reports(results, on_step=None, gazette=None, output_paths=None):
    """Write the two PCT deliverables and return (worked_path, not_found_path).

    - worked_<gazette>.xlsx    : rows where contacts were extracted (status found)
    - not_found_<gazette>.xlsx : the remaining rows (no contacts / errors)

    Both files are always produced (headers only when a bucket is empty) so the
    completion email can reliably attach both.
    """
    from .contact_policy import mark_repeated
    mark_repeated(results)
    found_rows = [r for r in results if r.get("status") == "found"]
    miss_rows = [r for r in results if r.get("status") != "found"]
    worked_target, missed_target = output_paths or (None, None)
    worked_path = generate_work_report(found_rows, on_step=on_step, gazette=gazette,
                                      kind="worked", target_path=worked_target)
    not_found_path = generate_work_report(miss_rows, on_step=on_step, gazette=gazette,
                                         kind="not_found", target_path=missed_target)
    return worked_path, not_found_path


def generate_work_report(results, on_step=None, gazette=None, kind="worked", target_path=None):
    """Generate a PCT report Excel matching the standard output format.

    ``kind`` selects which deliverable this is:
      - "worked"    -> worked_<gazette>.xlsx   (found rows)
      - "not_found" -> not_found_<gazette>.xlsx (misses)
    Named after the gazette when available; uploaded sheets with no gazette
    fall back to a dated name.
    """
    results = sorted(results, key=lambda item: item.get("row", 0))
    wb = openpyxl.Workbook()
    ws = wb.active

    # Sheet name reflects the deliverable, e.g. "Work Report DD-Month-YYYY".
    date_str = datetime.now().strftime("%d-%B-%Y")
    title_prefix = "Not Found" if kind == "not_found" else "Work Report"
    sheet_name = f"{title_prefix} {date_str}"
    ws.title = sheet_name[:31]

    # Write headers with bold font
    for col, header in enumerate(WORK_REPORT_HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)

    for i, r in enumerate(results, start=2):
        values = [r.get("patent_id", ""), r.get("title", ""), r.get("appl_no", ""),
                  r.get("applicant", ""), r.get("url", ""), r.get("category", ""),
                  "; ".join(r.get("phones", [])), "; ".join(r.get("emails", [])),
                  r.get("display_name", r.get("agent_name", "")), r.get("country", ""),
                  r.get("researcher", ""), r.get("priority_date", "")]
        for column, value in enumerate(values, 1):
            # XML 1.0 cannot store these non-printing control characters.
            # Clean only the exported cell; preserve source/evidence/journal data.
            if isinstance(value, str):
                from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
                value = ILLEGAL_CHARACTERS_RE.sub("", value)
            ws.cell(row=i, column=column, value=value)

    # PCT output files are local-only. The database may store metadata and
    # a local path, but the report sheet itself stays in this folder.
    output_dir = PCT_OUTPUT_DIR.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Filename: prefer the gazette (e.g. "worked_28-2025.xlsx" /
    # "not_found_28-2025.xlsx"); fall back to a dated name for uploaded sheets.
    gazette_slug = str(gazette or "").strip().replace("/", "-").replace("\\", "-").replace(" ", "")
    if kind == "not_found":
        base_name = f"not_found_{gazette_slug}" if gazette_slug else f"Not Found Report {date_str}"
    else:
        base_name = f"worked_{gazette_slug}" if gazette_slug else f"Work Report {date_str}"

    output_name = f"{base_name}.xlsx"
    output_path = output_dir / output_name
    counter = 2
    while not target_path and output_path.exists():
        output_name = f"{base_name} book{counter}.xlsx"
        output_path = output_dir / output_name
        counter += 1

    output_path = Path(target_path).resolve() if target_path else output_path.resolve()
    if output_path.suffix.lower() not in PCT_REPORT_EXTENSIONS:
        raise ValueError(f"Unsupported PCT output extension: {output_path.suffix}")
    if output_dir not in output_path.parents:
        raise ValueError("PCT output must be saved inside the local outputs folder")

    # Keep the previous checkpoint readable if saving is interrupted or Excel
    # has the destination open. Only the coordinator writes these workbooks.
    from uuid import uuid4
    temporary = output_path.with_name(f".{output_path.stem}.{uuid4().hex}.tmp.xlsx")
    try:
        wb.save(str(temporary))
        os.replace(temporary, output_path)
    finally:
        wb.close()
        temporary.unlink(missing_ok=True)

    if on_step:
        label = "Not-found list" if kind == "not_found" else "Work Report"
        on_step(f"[Output] {label} saved: {output_name} ({len(results)} rows)")

    return str(output_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _row_result(idx, row_data, url, country, status,
                emails=None, phones=None, name="", reason=""):
    """Build a standardised row result dict."""
    return {
        "row": idx,
        "patent_id": row_data["id"],
        "title": row_data["title"],
        "appl_no": row_data["appl_no"],
        "applicant": row_data["applicant"],
        "url": url,
        "country": "" if ai_enabled() else country,
        "status": status,
        "emails": emails or [],
        "phones": phones or [],
        "name": name,
        "reason": reason,
        "researcher": row_data.get("researcher", ""),
        "priority_date": row_data.get("priority_date", ""),
    }


def _failure(error_msg):
    """Build a standardised failure result."""
    return {
        "status": "failure",
        "error": error_msg,
        "results": [],
        "summary": {"total": 0, "found": 0, "not_found": 0, "errors": 0},
    }
