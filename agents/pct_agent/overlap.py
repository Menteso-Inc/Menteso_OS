"""One browser downloading ahead of bounded PDF verifiers, with a single writer.

The verifier runs two independent image requests concurrently. PDF rendering and
OCR stay isolated in each worker; Playwright stays on its owning thread. Pending work is
bounded so stopping cannot leave an unbounded verification backlog.
"""
import json
import os
import queue
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from pathlib import Path

from .browser import BrowserStopRequested


def bounded_setting(name, default, minimum, maximum, convert=float):
    try:
        return max(minimum, min(maximum, convert(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


class RowJournal:
    """Append every completed row before publishing it to the dashboard."""

    def __init__(self, path, input_file, total):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.append({"_meta": True, "input_file": str(input_file), "total": total,
                     "started": datetime.now(timezone.utc).isoformat(),
                     "mode": "single_browser_overlap"})

    def append(self, row):
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())


def process_rows(rows, browser, verify, make_result, on_result, step,
                 browser_event, stop_requested, run_id, max_pending=2,
                 min_interval=10.0, completed_rows=(), verification_workers=1,
                 api_concurrency=8):
    """Download on this thread, verify in isolated workers, collect only here.

    A stop stops new downloads and drains the bounded set already downloaded.
    Browser failures are errors unless the browser positively reports no PDF.
    One retry of transient failures uses the same browser with extra backoff.
    """
    verification_workers = max(1, min(4, int(verification_workers)))
    max_pending = max(verification_workers, min(8, int(max_pending)))
    messages = queue.Queue()
    pending = {}
    results = []
    total = len(rows)
    last_start = None
    interval = min_interval
    completed_rows = set(completed_rows)
    process_worker = None

    def relay():
        if process_worker is not None:
            for message in process_worker.drain_messages():
                step(message)
        while True:
            try:
                step(messages.get_nowait())
            except queue.Empty:
                return

    def pause(seconds):
        deadline = time.monotonic() + max(0, seconds)
        while time.monotonic() < deadline:
            relay()
            collect()
            if stop_requested():
                return False
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        return not stop_requested()

    def publish(row, url, contacts):
        result = make_result(row, url, contacts)
        # Persist and update reports on the coordinator, never worker threads.
        on_result(result)
        results.append(result)
        browser_event({"event": "contacts", "row": row["_row_idx"],
                       "total": total, "url": url, "patent_id": row["id"],
                       "status": result["status"], "emails": result.get("emails", []),
                       "phones": result.get("phones", []), "name": result.get("name", "")})
        step(f"[Row {row['_row_idx']}] {result['status'].upper()}: verification complete"
             if result["status"] == "found" else
             f"[Row {row['_row_idx']}] {result['status'].upper()}: {result.get('reason', '')}")

    def collect(block=False):
        relay()
        if not pending:
            return
        if block:
            wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
        for future in list(pending):
            if not future.done():
                continue
            row, url = pending.pop(future)
            try:
                contacts = future.result()
            except Exception as exc:
                contacts = {"status": "error", "reason": f"verification_exception: {type(exc).__name__}",
                            "ai_status": "needs_review"}
            publish(row, url, contacts)
        relay()

    def verify_row(path, row):
        def log(message):
            messages.put(f"[Row {row['_row_idx']}] {message}")
        log("[PDF Extractor] Extracting and verifying downloaded PDF")
        return verify(path, on_step=log, context=dict(row))

    if verification_workers > 1:
        from .parallel_verifier import ProcessVerifier
        executor = ProcessVerifier(verification_workers, api_concurrency)
    else:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pct-pdf-verifier")
    with executor as worker:
        if verification_workers > 1:
            process_worker = worker
        try:
            for index, source in enumerate(rows, 1):
                if index in completed_rows:
                    continue
                while len(pending) >= max_pending and not stop_requested():
                    collect(block=True)
                collect()
                if stop_requested():
                    break
                row = {**source, "_row_idx": index}
                url = "https://patentscope.wipo.int/search/en/" + row["id"].replace("/", "")
                # Duplicate patents must never overwrite a PDF being verified.
                doc_id = f"{row['id'].replace('/', '_')}_{run_id}_row{index}"
                pdf_path = None
                failure = "scrape_failed"
                for attempt in range(2):
                    delay = 0 if last_start is None else interval - (time.monotonic() - last_start)
                    if not pause(delay):
                        break
                    last_start = time.monotonic()
                    browser_event({"event": "navigate", "row": index, "total": total,
                                   "url": url, "patent_id": row["id"]})
                    step(f"[Row {index}/{total}] Downloading: {row['id']} (attempt {attempt + 1})")
                    try:
                        pdf_path = browser.scrape_patent(url, doc_id, on_step=step)
                        failure = getattr(browser, "last_failure_reason", "") or "scrape_failed"
                    except BrowserStopRequested:
                        raise
                    except Exception as exc:
                        failure = f"scrape_exception: {type(exc).__name__}"
                    collect()
                    if pdf_path:
                        interval = max(min_interval, interval * 0.75)
                        break
                    if failure == "no_pdf_row":
                        break
                    interval = min(60.0, max(10.0, interval * 2))
                    if attempt == 0 and not stop_requested():
                        step(f"[Row {index}] {failure}; retrying the same row with backoff")
                if stop_requested() and not pdf_path:
                    break
                if pdf_path:
                    future = (worker.submit(pdf_path, row) if process_worker is not None
                              else worker.submit(verify_row, pdf_path, row))
                    pending[future] = (row, url)
                else:
                    publish(row, url, {"status": "not_found" if failure == "no_pdf_row" else "error",
                                       "reason": failure, "ai_status": "needs_review"})
                collect()
        except BrowserStopRequested:
            step("[Pipeline] Stop requested; saving verification of PDFs already downloaded")
        finally:
            # Drain even on browser failure so finished PDFs are never lost.
            while pending:
                collect(block=True)
            relay()
    return sorted(results, key=lambda result: result["row"])
