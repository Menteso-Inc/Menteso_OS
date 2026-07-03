"""
PCT Agent — High-Performance Parallel Pipeline
3-stage architecture: Browser (find PDF URL) → Download → OCR
All stages run concurrently.  Contact caching skips known firms.

Target: 500+ rows/min with 20 browser tabs.
"""
import json
import os
import time
import threading
import queue
import re
from pathlib import Path
from datetime import datetime, timezone

from .browser import (
    create_browser_pool, close_browser_pool,
    scrape_pdf_url_only, download_pdf_standalone, DOWNLOADS_DIR,
)
from .pdf_extractor import extract_contacts_from_pdf


PROJECT_DIR = Path(__file__).parent.parent.parent
OUTPUTS_DIR = PROJECT_DIR / "outputs" / "pct-work-sheets"
RESULT_STATUS_PRIORITY = {
    "found": 3,
    "not_found": 2,
    "error": 1,
}


# ---------------------------------------------------------------------------
# Thread-safe stats
# ---------------------------------------------------------------------------
class PipelineStats:
    __slots__ = (
        "_lock", "total", "completed", "found", "not_found", "errors",
        "skipped", "cached", "browse_active", "dl_active", "ocr_active",
        "start_time",
    )

    def __init__(self, total):
        self._lock = threading.Lock()
        self.total = total
        self.completed = 0
        self.found = 0
        self.not_found = 0
        self.errors = 0
        self.skipped = 0
        self.cached = 0
        self.browse_active = 0
        self.dl_active = 0
        self.ocr_active = 0
        self.start_time = time.time()

    def record(self, status, from_cache=False):
        with self._lock:
            self.completed += 1
            if from_cache:
                self.cached += 1
            if status == "found":
                self.found += 1
            elif status == "not_found":
                self.not_found += 1
            else:
                self.errors += 1

    def snapshot(self):
        with self._lock:
            elapsed = max(time.time() - self.start_time, 0.1)
            done = self.completed + self.skipped
            rate = (self.completed / elapsed) * 60 if self.completed else 0
            remaining = self.total - done
            eta = (remaining / rate) if rate > 0 else 0
            return {
                "type": "pipeline_stats",
                "total": self.total,
                "completed": done,
                "found": self.found,
                "not_found": self.not_found,
                "errors": self.errors,
                "skipped": self.skipped,
                "cached": self.cached,
                "rows_per_minute": round(rate, 1),
                "eta_minutes": round(eta, 1),
                "elapsed_seconds": round(elapsed),
                "browse_active": self.browse_active,
                "dl_active": self.dl_active,
                "ocr_active": self.ocr_active,
                "captcha_state": "ok",
                "captcha_cooldown_remaining": 0,
            }


# ---------------------------------------------------------------------------
# CAPTCHA coordination — fast backoff
# ---------------------------------------------------------------------------
class CaptchaCoordinator:
    def __init__(self, on_step=None):
        self._lock = threading.Lock()
        self._cooldown_until = 0.0
        self._consecutive = 0
        self._step = on_step or (lambda m: None)

    def report_captcha(self):
        with self._lock:
            self._consecutive += 1
            # Fast backoff: 15s → 30s → 60s → 90s cap
            backoff = min(15 * (2 ** (self._consecutive - 1)), 90)
            self._cooldown_until = time.time() + backoff
            self._step(
                f"[Pipeline] CAPTCHA — all tabs pausing {backoff}s "
                f"(hit #{self._consecutive})"
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


# ---------------------------------------------------------------------------
# Contact cache — skip scraping for known applicants/firms
# ---------------------------------------------------------------------------
class ContactCache:
    """Thread-safe cache keyed by applicant name.
    If we already extracted contacts for a firm, reuse them.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._cache = {}  # applicant_name -> {emails, phones, name, status}

    def get(self, applicant):
        key = self._normalize(applicant)
        if not key:
            return None
        with self._lock:
            return self._cache.get(key)

    def put(self, applicant, contacts):
        key = self._normalize(applicant)
        if not key or contacts.get("status") != "found":
            return
        # Only cache if we have at least an email
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
        # Normalize: strip, lowercase, remove common suffixes
        s = applicant.strip().lower()
        for suffix in (" gmbh", " ag", " pty ltd", " ltd", " inc", " co"):
            s = s.replace(suffix, "")
        return s.strip() if len(s) > 3 else None


# ---------------------------------------------------------------------------
# Progress file (JSONL, append-only)
# ---------------------------------------------------------------------------
class ProgressFile:
    def __init__(self, run_id, input_file, total):
        OUTPUTS_DIR.mkdir(exist_ok=True)
        self._path = OUTPUTS_DIR / f"pct_progress_{run_id}.jsonl"
        self._lock = threading.Lock()
        self._append({"_meta": True, "input_file": str(input_file),
                       "total": total, "started": datetime.now(timezone.utc).isoformat()})

    def append_result(self, result):
        self._append(result)

    def _append(self, obj):
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    @property
    def path(self):
        return str(self._path)

    @staticmethod
    def load_completed(progress_path):
        done = set()
        try:
            with open(progress_path, encoding="utf-8") as f:
                for line in f:
                    obj = json.loads(line.strip())
                    if not obj.get("_meta") and obj.get("patent_id"):
                        done.add(obj["patent_id"])
        except Exception:
            pass
        return done

    @staticmethod
    def find_latest(input_file):
        OUTPUTS_DIR.mkdir(exist_ok=True)
        candidates = sorted(OUTPUTS_DIR.glob("pct_progress_*.jsonl"), reverse=True)
        for path in candidates:
            try:
                with open(path, encoding="utf-8") as f:
                    first = json.loads(f.readline())
                if first.get("_meta") and first.get("input_file") == str(input_file):
                    return str(path)
            except Exception:
                continue
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _id_to_url(patent_id):
    return f"https://patentscope.wipo.int/search/en/{patent_id.replace('/', '')}"


def _extract_country(appl_no):
    m = re.match(r'^([A-Z]{2})', str(appl_no).strip())
    return m.group(1) if m else ""


REASON_LABELS = {
    "no_pdf_row": "no RO/101/306/Request-form PDF on this patent page",
    "pdf_no_contacts": "PDF found but no email/phone inside",
    "throttled": "WIPO returned an empty page (throttled)",
    "load_timeout": "patent page never finished loading",
    "nav_failed": "navigation to WIPO failed",
    "docs_tab": "Documents tab did not open",
    "captcha": "captcha challenge",
    "captcha_persistent": "captcha unsolved after multiple attempts",
    "download_failed": "PDF URL found but download failed",
    "exception": "unhandled scrape exception",
}


def _humanize_reason(reason):
    """Map a reason code to a short user-facing explanation. Unknown codes
    fall back to the raw code so they're still visible in the log.
    """
    if not reason:
        return ""
    raw = reason.strip()
    # Compound prefixes (e.g. "scrape_exception: ...", "ocr_exception: ...")
    # — show only the leading category so the log line stays readable.
    for prefix in ("scrape_exception", "ocr_exception"):
        if raw.startswith(prefix):
            return REASON_LABELS.get("exception", prefix)
    return REASON_LABELS.get(raw, raw)


def _make_result(row_data, url, country, status, emails=None, phones=None, name=""):
    return {
        "row": row_data.get("_row_idx", 0),
        "patent_id": row_data["id"],
        "title": row_data["title"],
        "appl_no": row_data["appl_no"],
        "applicant": row_data["applicant"],
        "url": url,
        "country": country,
        "status": status,
        "emails": emails or [],
        "phones": phones or [],
        "name": name,
    }


def dedupe_results_by_row(results):
    """
    Keep exactly one result per original row number.
    If a row appears more than once, prefer found > not_found > error.
    """
    merged = {}
    duplicates_resolved = 0

    for result in results:
        row_no = result.get("row")
        if row_no is None:
            continue

        current = merged.get(row_no)
        if current is None:
            merged[row_no] = result
            continue

        duplicates_resolved += 1
        current_score = RESULT_STATUS_PRIORITY.get(current.get("status"), 0)
        candidate_score = RESULT_STATUS_PRIORITY.get(result.get("status"), 0)
        if candidate_score > current_score:
            merged[row_no] = result

    ordered = [merged[row_no] for row_no in sorted(merged)]
    return ordered, duplicates_resolved


# ---------------------------------------------------------------------------
# 3-Stage Pipeline
# ---------------------------------------------------------------------------
class PipelinePCT:
    """High-performance 3-stage pipeline:
    Stage 1: Browser workers (find PDF URLs)
    Stage 2: Download workers (HTTP download PDFs)
    Stage 3: OCR workers (extract contacts)
    + Contact cache to skip known applicants.
    """

    def __init__(self, patent_rows, on_step, browser_workers=20, download_workers=30,
                 ocr_workers=8, headless=True, resume_path=None, input_file="",
                 live_level_getter=None, shared_cache=None, shared_captcha=None):
        self.patent_rows = patent_rows
        self.on_step = on_step
        self.n_browser = browser_workers
        self.n_download = download_workers
        self.n_ocr = ocr_workers
        self.headless = headless
        self.input_file = input_file
        # Lets pool workers detect when the user dragged the slider down to
        # L1 Safe mid-run so they can drain instead of hammering WIPO.
        self.live_level_getter = live_level_getter

        # Bounded queues — prevent memory bloat
        self.browse_queue = queue.Queue()
        self.download_queue = queue.Queue(maxsize=200)
        self.ocr_queue = queue.Queue(maxsize=200)

        # Coordination — prefer shared objects from ChunkedPipelineManager so
        # every parallel pipeline pauses together on captcha and reuses
        # applicant contacts. Fall back to local instances when run standalone.
        self.stats = PipelineStats(len(patent_rows))
        self.captcha = shared_captcha or CaptchaCoordinator(on_step=on_step)
        self.cache = shared_cache or ContactCache()
        self._shutdown = threading.Event()

        # Resume
        self._completed_ids = set()
        if resume_path:
            self._completed_ids = ProgressFile.load_completed(resume_path)
            self.stats.skipped = len(self._completed_ids)

        # Results
        self._results = []
        self._results_lock = threading.Lock()

        # Progress
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.progress = ProgressFile(run_id, input_file, len(patent_rows))

    def step(self, msg):
        if self.on_step:
            self.on_step(msg)

    def run(self):
        """Execute the 3-stage pipeline.  Returns list of result dicts."""
        # Fill browse queue, skip completed and cached
        queued = 0
        cache_hits = 0
        for idx, row in enumerate(self.patent_rows, start=1):
            row.setdefault("_row_idx", idx)
            if row["id"] in self._completed_ids:
                continue

            # Check contact cache by applicant
            cached = self.cache.get(row.get("applicant", ""))
            if cached:
                url = _id_to_url(row["id"])
                country = _extract_country(row["appl_no"])
                result = _make_result(
                    row, url, country, cached["status"],
                    emails=cached["emails"], phones=cached["phones"],
                    name=cached["name"],
                )
                self._collect_result(result, from_cache=True)
                cache_hits += 1
                continue

            self.browse_queue.put(row)
            queued += 1

        if queued == 0 and cache_hits == 0:
            self.step("[Pipeline] All rows already completed")
            return self._load_existing_results()

        self.step(
            f"[Pipeline] {queued} to scrape, {cache_hits} from cache, "
            f"{self.stats.skipped} from resume"
        )

        # Sentinels for browser workers
        for _ in range(self.n_browser):
            self.browse_queue.put(None)

        # Launch browser pool
        self.step(f"[Pipeline] Launching {self.n_browser} browser tabs...")
        pw, browser, pages, page_proxies = create_browser_pool(self.n_browser, self.headless)
        self._page_proxies = page_proxies
        active_proxies = sum(1 for p in page_proxies if p)
        if active_proxies:
            self.step(f"[Pipeline] {active_proxies}/{self.n_browser} tabs on rotating proxy IPs")

        try:
            threads = []

            # Stage 1: Browser workers
            for i in range(self.n_browser):
                t = threading.Thread(
                    target=self._browser_worker, args=(i, pages[i]),
                    daemon=True,
                )
                threads.append(t)

            # Stage 2: Download workers
            for i in range(self.n_download):
                t = threading.Thread(
                    target=self._download_worker, args=(i,),
                    daemon=True,
                )
                threads.append(t)

            # Stage 3: OCR workers
            for i in range(self.n_ocr):
                t = threading.Thread(
                    target=self._ocr_worker, args=(i,),
                    daemon=True,
                )
                threads.append(t)

            # Stats reporter
            stats_t = threading.Thread(target=self._stats_reporter, daemon=True)
            threads.append(stats_t)

            for t in threads:
                t.start()

            self.step("[Pipeline] All workers started — processing...")

            # Wait for Stage 1 (browser)
            for t in threads[:self.n_browser]:
                t.join()

            # Signal Stage 2 (download) to stop
            for _ in range(self.n_download):
                self.download_queue.put(None)
            for t in threads[self.n_browser:self.n_browser + self.n_download]:
                t.join()

            # Signal Stage 3 (OCR) to stop
            for _ in range(self.n_ocr):
                self.ocr_queue.put(None)
            for t in threads[self.n_browser + self.n_download:
                             self.n_browser + self.n_download + self.n_ocr]:
                t.join()

            self._shutdown.set()
            stats_t.join(timeout=3)

        finally:
            close_browser_pool(pw, browser)

        # Merge with resume results
        if self._completed_ids:
            existing = self._load_existing_results()
            all_results = existing + self._results
        else:
            all_results = self._results

        all_results, duplicates_resolved = dedupe_results_by_row(all_results)

        snap = self.stats.snapshot()
        self.step(
            f"[Pipeline] DONE — {snap['found']} found, {snap['not_found']} not found, "
            f"{snap['errors']} errors, {snap['cached']} cached | "
            f"{snap['elapsed_seconds']}s ({snap['rows_per_minute']} rows/min)"
        )
        if duplicates_resolved:
            self.step(f"[Pipeline] Resolved {duplicates_resolved} duplicate row results during merge")
        return all_results

    # -- Stage 1: Browser workers --

    # Cap how many times a single row can be re-queued after a captcha-failed
    # scrape. After this many tries we accept that the solver can't get past
    # it for this row, record an error result, and move on. This prevents a
    # persistent block (IP banned, page changed) from looping forever.
    MAX_CAPTCHA_RETRIES_PER_ROW = 3

    # Adaptive backoff: only triggered by SYSTEM-failure reasons (WIPO
    # throttling, navigation timeouts, captcha blocks). Legitimate misses
    # (page loaded fine but the patent simply has no RO/101/306/Request-form
    # PDF) do NOT count — they're just data, not a signal that WIPO is angry.
    BACKOFF_AFTER_FAILURES = 3      # streak threshold
    BACKOFF_BASE_SECONDS = 4.0      # multiplied by (streak - threshold)
    BACKOFF_CAP_SECONDS = 60.0      # never sleep longer than this

    # Reasons that mean "WIPO/network failure" — counts toward the backoff
    # streak. Anything else (notably "no_pdf_row") is a legitimate miss and
    # is intentionally excluded.
    SYSTEM_FAIL_REASONS_BROWSER = (
        "throttled",
        "load_timeout",
        "nav_failed",
        "docs_tab",
    )

    def _browser_worker(self, wid, page):
        consecutive_failures = 0
        while True:
            row_data = self.browse_queue.get()
            if row_data is None:
                break

            # Live downgrade check — if the user dragged the slider to Safe
            # (L1) mid-run, this worker stops pulling new rows. The pool
            # drains naturally as workers exit.
            if callable(self.live_level_getter):
                try:
                    live = self.live_level_getter()
                except Exception:
                    live = None
                if live == 1:
                    self.step(
                        f"[Worker {wid}] User dragged to L1 Safe — "
                        f"exiting pool worker, remaining rows will re-queue"
                    )
                    # Put row back so a future sequential pass can pick it up
                    self.browse_queue.put(row_data)
                    break

            # Adaptive backoff — only kicks in when the recent failures
            # were SYSTEM failures (WIPO throttle, nav timeout, captcha
            # block). A run of genuine "no PDF on this patent page"
            # results does NOT count and will not slow the worker down.
            if consecutive_failures >= self.BACKOFF_AFTER_FAILURES:
                backoff = min(
                    self.BACKOFF_CAP_SECONDS,
                    self.BACKOFF_BASE_SECONDS * (consecutive_failures - self.BACKOFF_AFTER_FAILURES + 1),
                )
                self.step(
                    f"[Worker {wid}] {consecutive_failures} consecutive SYSTEM failures "
                    f"(WIPO throttle / timeout) — backing off {backoff:.0f}s"
                )
                time.sleep(backoff)

            self.captcha.wait_if_cooling()

            patent_id = row_data["id"]
            url = _id_to_url(patent_id)
            doc_id = patent_id.replace("/", "_")
            country = _extract_country(row_data["appl_no"])

            # Fire a "navigate" browser event so the Scraping Browser
            # preview panel shows what this pool worker is currently
            # working on (otherwise the preview just sits idle in pool
            # mode, even though many rows are being scraped).
            try:
                self.on_step({
                    "type": "browser",
                    "event": "navigate",
                    "url": url,
                    "row": row_data.get("_row_idx", 0),
                    "total": self.stats.total,
                    "patent_id": patent_id,
                    "title": row_data.get("title", ""),
                    "applicant": row_data.get("applicant", ""),
                    "country": country,
                })
            except Exception:
                pass

            with self.stats._lock:
                self.stats.browse_active += 1

            scrape_error = None
            scrape_reason = ""
            try:
                pdf_url, cookies, captcha, scrape_reason = scrape_pdf_url_only(
                    page, url, on_step=self.step,
                )
            except Exception as e:
                pdf_url, cookies, captcha = None, {}, False
                scrape_error = str(e)
                scrape_reason = "exception"

            with self.stats._lock:
                self.stats.browse_active -= 1

            if captcha:
                self.captcha.report_captcha()
                retries = row_data.get("_captcha_retries", 0) + 1
                row_data["_captcha_retries"] = retries
                if retries >= self.MAX_CAPTCHA_RETRIES_PER_ROW:
                    self.step(
                        f"[Pipeline] Row {row_data.get('_row_idx', '?')} "
                        f"({patent_id}) — captcha unsolved after {retries} attempts, "
                        f"recording as error and moving on"
                    )
                    result = _make_result(row_data, url, country, "error")
                    result["reason"] = "captcha_persistent"
                    self._collect_result(result)
                else:
                    self.browse_queue.put(row_data)
                continue

            self.captcha.report_clear()

            if pdf_url:
                # Push to download queue (Stage 2). Carry this worker's proxy so
                # the PDF downloads from the SAME exit IP that discovered it.
                worker_proxy = None
                page_proxies = getattr(self, "_page_proxies", None)
                if page_proxies and wid < len(page_proxies):
                    worker_proxy = page_proxies[wid]
                self.download_queue.put((row_data, url, country, doc_id, pdf_url, cookies, worker_proxy))
                consecutive_failures = 0  # success path resets the counter
            elif scrape_error:
                result = _make_result(row_data, url, country, "error")
                result["reason"] = f"scrape_exception: {scrape_error[:200]}"
                self._collect_result(result)
                # An unhandled exception is treated as a system failure.
                consecutive_failures += 1
                self._emit_browser_no_pdf(row_data, url, patent_id)
            else:
                # Stamp the diagnostic reason so the retry pass can decide
                # whether this row is worth re-scraping, AND so the
                # backoff streak only triggers on actual system failures.
                result = _make_result(row_data, url, country, "not_found")
                final_reason = scrape_reason or "no_pdf_row"
                result["reason"] = final_reason
                self._collect_result(result)

                # Only system failures count toward the backoff streak.
                # "no_pdf_row" means WIPO served the page correctly and the
                # patent just doesn't have an RO/101/306/Request-form PDF —
                # zero reason to sleep the worker over that.
                if final_reason in self.SYSTEM_FAIL_REASONS_BROWSER:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

                self._emit_browser_no_pdf(row_data, url, patent_id)

    def _emit_browser_no_pdf(self, row_data, url, patent_id):
        """Surface a 'no_pdf' status in the Scraping Browser panel so the
        preview shows what each pool worker just produced."""
        try:
            self.on_step({
                "type": "browser",
                "event": "no_pdf",
                "url": url,
                "row": row_data.get("_row_idx", 0),
                "total": self.stats.total,
                "patent_id": patent_id,
            })
        except Exception:
            pass

    # -- Stage 2: Download workers --

    def _download_worker(self, wid):
        while True:
            item = self.download_queue.get()
            if item is None:
                break

            # Back-compat: older tuples had no proxy element.
            if len(item) == 7:
                row_data, url, country, doc_id, pdf_url, cookies, worker_proxy = item
            else:
                row_data, url, country, doc_id, pdf_url, cookies = item
                worker_proxy = None

            with self.stats._lock:
                self.stats.dl_active += 1

            try:
                pdf_path = download_pdf_standalone(pdf_url, cookies, doc_id, proxy=worker_proxy)
            except Exception:
                pdf_path = None

            with self.stats._lock:
                self.stats.dl_active -= 1

            if pdf_path:
                # Push to OCR queue (Stage 3)
                self.ocr_queue.put((row_data, url, country, pdf_path))
            else:
                # PDF URL was discovered but HTTP download failed —
                # treat as a system failure (worth retrying) rather than
                # a genuine "no document on the page" miss.
                result = _make_result(row_data, url, country, "not_found")
                result["reason"] = "download_failed"
                self._collect_result(result)

    # -- Stage 3: OCR workers --

    def _ocr_worker(self, wid):
        while True:
            item = self.ocr_queue.get()
            if item is None:
                break

            row_data, url, country, pdf_path = item

            with self.stats._lock:
                self.stats.ocr_active += 1

            ocr_exception = None
            try:
                contacts = extract_contacts_from_pdf(pdf_path)
            except Exception as e:
                ocr_exception = str(e)
                contacts = {"status": "error", "emails": [], "phones": [], "name": ""}

            with self.stats._lock:
                self.stats.ocr_active -= 1

            # Cache result for this applicant
            self.cache.put(row_data.get("applicant", ""), contacts)

            result = _make_result(
                row_data, url, country, contacts["status"],
                emails=contacts.get("emails", []),
                phones=contacts.get("phones", []),
                name=contacts.get("name", ""),
            )
            # Stamp the actual reason so the user sees "PDF parsed, no
            # email/phone inside" rather than a generic not_found. The
            # retry pass also uses this — pdf_no_contacts is NOT worth
            # re-scraping (the PDF won't grow new emails on retry).
            if contacts["status"] == "not_found":
                result["reason"] = "pdf_no_contacts"
            elif contacts["status"] == "error":
                result["reason"] = (
                    f"ocr_exception: {ocr_exception[:200]}"
                    if ocr_exception else "ocr_error"
                )
            self._collect_result(result)

            # Fire "contacts" browser event so the dashboard's Scraping
            # Browser panel reflects the latest extraction (was idle in
            # pool mode before this).
            try:
                self.on_step({
                    "type": "browser",
                    "event": "contacts",
                    "url": url,
                    "row": row_data.get("_row_idx", 0),
                    "total": self.stats.total,
                    "patent_id": row_data.get("id", ""),
                    "title": row_data.get("title", ""),
                    "emails": contacts.get("emails", []),
                    "phones": contacts.get("phones", []),
                    "name": contacts.get("name", ""),
                    "status": contacts.get("status", ""),
                    "found_count": self.stats.found,
                    "not_found_count": self.stats.not_found,
                    "error_count": self.stats.errors,
                })
            except Exception:
                pass

            # Cleanup PDF to save disk space
            try:
                os.remove(pdf_path)
            except Exception:
                pass

    # -- Result collection --

    def _collect_result(self, result, from_cache=False):
        with self._results_lock:
            self._results.append(result)

        self.stats.record(result["status"], from_cache=from_cache)
        self.progress.append_result(result)

        tag = "+" if result["status"] == "found" else "-"
        emails_str = ", ".join(result["emails"][:2]) if result["emails"] else "-"
        src = " [cache]" if from_cache else ""
        # Surface the diagnostic reason so the user can tell at a glance
        # WHY a row missed: was WIPO throttling us, did the patent simply
        # not have a Request-form PDF, or did the PDF have no emails?
        reason = (result.get("reason") or "").strip()
        reason_text = _humanize_reason(reason) if reason else ""
        suffix = f" | {reason_text}" if reason_text else ""
        self.step(
            f"[{tag}] Row {result['row']}: {result['patent_id']} — "
            f"{result['status']} | {emails_str}{src}{suffix}"
        )

    def _stats_reporter(self):
        while not self._shutdown.is_set():
            snap = self.stats.snapshot()
            snap["captcha_state"] = self.captcha.state
            snap["captcha_cooldown_remaining"] = round(self.captcha.cooldown_remaining())
            snap["browse_queue"] = self.browse_queue.qsize()
            snap["dl_queue"] = self.download_queue.qsize()
            snap["ocr_queue"] = self.ocr_queue.qsize()
            self.step(snap)
            self._shutdown.wait(timeout=2)

    def _load_existing_results(self):
        results = []
        latest = ProgressFile.find_latest(self.input_file)
        if not latest:
            return results
        try:
            with open(latest, encoding="utf-8") as f:
                for line in f:
                    obj = json.loads(line.strip())
                    if not obj.get("_meta"):
                        results.append(obj)
        except Exception:
            pass
        return results


class ChunkedPipelineManager:
    """
    Split large spreadsheets into stable row chunks and assign each chunk
    to its own pipeline worker. Final output is merged by original row number.
    """

    def __init__(
        self,
        patent_rows,
        on_step,
        input_file="",
        chunk_size=400,
        parallel_pipelines=2,
        browser_workers=6,
        download_workers=8,
        ocr_workers=4,
        headless=False,
        resume_path=None,
        live_level_getter=None,
    ):
        self.patent_rows = patent_rows
        self.on_step = on_step
        self.input_file = input_file
        self.chunk_size = max(1, chunk_size)
        self.parallel_pipelines = max(1, parallel_pipelines)
        self.browser_workers = max(1, browser_workers)
        self.download_workers = max(1, download_workers)
        self.ocr_workers = max(1, ocr_workers)
        self.resume_path = resume_path
        self.live_level_getter = live_level_getter

        for idx, row in enumerate(self.patent_rows, start=1):
            row["_row_idx"] = idx

        self.chunks = [
            self.patent_rows[i:i + self.chunk_size]
            for i in range(0, len(self.patent_rows), self.chunk_size)
        ]
        self.parallel_pipelines = min(self.parallel_pipelines, len(self.chunks)) or 1
        self.browser_workers = max(2, self.browser_workers // self.parallel_pipelines)
        self.download_workers = max(3, self.download_workers // self.parallel_pipelines)
        self.ocr_workers = max(2, self.ocr_workers // self.parallel_pipelines)
        # Honor whatever the caller passed in. Previously forced to False
        # because WIPO captchas required a human; now the captcha_solver
        # sub-agent handles them so headless is fine and 2-3× faster.
        self.headless = headless

        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._chunk_snapshots = {}
        self._results_by_row = {}
        self._chunk_queue = queue.Queue()
        self._duplicate_rows_resolved = 0
        self._chunk_errors = []
        self._start_time = time.time()

        # Cross-pipeline coordination: one shared cache + one shared captcha
        # cooldown for ALL parallel pipelines spawned by this manager. Without
        # this every PipelinePCT had its own — captcha hits in one pipeline
        # didn't pause the others, and the same applicant was scraped
        # multiple times across pipelines.
        from shared.pct_coordinator import (
            SharedContactCache,
            SharedCaptchaCoordinator,
        )
        self._shared_cache = SharedContactCache()
        self._shared_captcha = SharedCaptchaCoordinator(on_step=on_step)

    def step(self, msg):
        if self.on_step:
            self.on_step(msg)

    def run(self):
        total_chunks = len(self.chunks)
        if total_chunks == 0:
            return []

        self.step(
            f"[Chunk Manager] Split {len(self.patent_rows)} rows into {total_chunks} chunk(s) "
            f"of up to {self.chunk_size} rows"
        )
        self.step(
            f"[Chunk Manager] Running up to {min(self.parallel_pipelines, total_chunks)} "
            f"chunk pipeline(s) in parallel"
        )
        self.step(
            f"[Chunk Manager] Per chunk workers: {self.browser_workers} browsers, "
            f"{self.download_workers} downloaders, {self.ocr_workers} OCR"
        )
        if self.resume_path:
            self.step("[Chunk Manager] Resume files are ignored in chunk mode to prevent duplicate merges")

        for chunk_idx, chunk_rows in enumerate(self.chunks, start=1):
            self._chunk_queue.put((chunk_idx, chunk_rows))
        for _ in range(min(self.parallel_pipelines, total_chunks)):
            self._chunk_queue.put(None)

        workers = []
        for worker_id in range(min(self.parallel_pipelines, total_chunks)):
            t = threading.Thread(
                target=self._chunk_worker,
                args=(worker_id + 1, total_chunks),
                daemon=True,
            )
            workers.append(t)

        stats_t = threading.Thread(target=self._stats_reporter, daemon=True)
        stats_t.start()

        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        self._shutdown.set()
        stats_t.join(timeout=3)

        if self._chunk_errors:
            joined = "; ".join(self._chunk_errors[:3])
            self.step(f"[Chunk Manager] {len(self._chunk_errors)} chunk pipeline(s) failed: {joined}")

        merged_results = [self._results_by_row[row_no] for row_no in sorted(self._results_by_row)]
        merged_results, extra_dupes = dedupe_results_by_row(merged_results)
        total_dupes = self._duplicate_rows_resolved + extra_dupes
        if total_dupes:
            self.step(f"[Chunk Manager] Resolved {total_dupes} duplicate row result(s)")

        self._emit_snapshot(force=True)
        return merged_results

    def _chunk_worker(self, worker_id, total_chunks):
        while True:
            # Live downgrade check BEFORE pulling another chunk. If the
            # user dragged the slider to L1 Safe, stop launching new
            # PipelinePCT instances — otherwise the chunk loop keeps
            # creating pools that immediately exit, spamming the log
            # and producing no useful work.
            if callable(self.live_level_getter):
                try:
                    live = self.live_level_getter()
                except Exception:
                    live = None
                if live == 1:
                    self.step(
                        f"[Chunk Manager worker {worker_id}] User at L1 Safe — "
                        f"stopping chunk dispatch. Remaining rows will be "
                        f"handed back to sequential mode."
                    )
                    return

            item = self._chunk_queue.get()
            if item is None:
                return

            chunk_idx, chunk_rows = item
            first_row = chunk_rows[0]["_row_idx"]
            last_row = chunk_rows[-1]["_row_idx"]
            self.step(
                f"[Chunk {chunk_idx}/{total_chunks}] Starting rows {first_row}-{last_row} "
                f"({len(chunk_rows)} rows)"
            )

            def chunk_step(message):
                # Pipeline stats are merged into the chunk-manager snapshot.
                if isinstance(message, dict) and message.get("type") == "pipeline_stats":
                    with self._lock:
                        self._chunk_snapshots[chunk_idx] = message
                    return
                # Browser events (and any other structured dict) must reach
                # the UI verbatim — wrapping them in an f-string here was
                # stringifying them into the execution log and breaking the
                # Scraping Browser panel in pool mode.
                if isinstance(message, dict):
                    self.step(message)
                    return
                self.step(f"[Chunk {chunk_idx}/{total_chunks}] {message}")

            pipeline = PipelinePCT(
                patent_rows=chunk_rows,
                on_step=chunk_step,
                browser_workers=self.browser_workers,
                download_workers=self.download_workers,
                ocr_workers=self.ocr_workers,
                headless=self.headless,
                resume_path=None,
                input_file=f"{self.input_file}::chunk{chunk_idx}",
                live_level_getter=self.live_level_getter,
                shared_cache=self._shared_cache,
                shared_captcha=self._shared_captcha,
            )

            try:
                chunk_results = pipeline.run()
                self._merge_chunk_results(chunk_idx, chunk_results)
                self.step(
                    f"[Chunk {chunk_idx}/{total_chunks}] Completed with {len(chunk_results)} result row(s)"
                )
            except Exception as exc:
                with self._lock:
                    self._chunk_errors.append(f"chunk {chunk_idx}: {exc}")
                self.step(f"[Chunk {chunk_idx}/{total_chunks}] ERROR: {exc}")
            finally:
                with self._lock:
                    self._chunk_snapshots.pop(chunk_idx, None)

    def _merge_chunk_results(self, chunk_idx, results):
        with self._lock:
            for result in results:
                row_no = result.get("row")
                if row_no is None:
                    continue
                current = self._results_by_row.get(row_no)
                if current is None:
                    self._results_by_row[row_no] = result
                    continue

                self._duplicate_rows_resolved += 1
                current_score = RESULT_STATUS_PRIORITY.get(current.get("status"), 0)
                candidate_score = RESULT_STATUS_PRIORITY.get(result.get("status"), 0)
                if candidate_score > current_score:
                    self._results_by_row[row_no] = result

    def _emit_snapshot(self, force=False):
        with self._lock:
            completed = sum(snap.get("completed", 0) for snap in self._chunk_snapshots.values())
            found = sum(snap.get("found", 0) for snap in self._chunk_snapshots.values())
            not_found = sum(snap.get("not_found", 0) for snap in self._chunk_snapshots.values())
            errors = sum(snap.get("errors", 0) for snap in self._chunk_snapshots.values())
            skipped = sum(snap.get("skipped", 0) for snap in self._chunk_snapshots.values())
            browse_active = sum(snap.get("browse_active", 0) for snap in self._chunk_snapshots.values())
            dl_active = sum(snap.get("dl_active", 0) for snap in self._chunk_snapshots.values())
            ocr_active = sum(snap.get("ocr_active", 0) for snap in self._chunk_snapshots.values())

            merged_count = len(self._results_by_row)
            completed = max(completed, merged_count)
            found = max(found, sum(1 for r in self._results_by_row.values() if r.get("status") == "found"))
            not_found = max(
                not_found,
                sum(1 for r in self._results_by_row.values() if r.get("status") == "not_found"),
            )
            errors = max(
                errors,
                sum(1 for r in self._results_by_row.values() if r.get("status") not in ("found", "not_found")),
            )

        elapsed = max(time.time() - self._start_time, 0.1)
        rate = (completed / elapsed) * 60 if completed else 0
        remaining = max(len(self.patent_rows) - completed, 0)
        eta = (remaining / rate) if rate > 0 else 0

        if force or completed or browse_active or dl_active or ocr_active:
            self.step({
                "type": "pipeline_stats",
                "total": len(self.patent_rows),
                "completed": completed,
                "found": found,
                "not_found": not_found,
                "errors": errors,
                "skipped": skipped,
                "cached": 0,
                "rows_per_minute": round(rate, 1),
                "eta_minutes": round(eta, 1),
                "elapsed_seconds": round(elapsed),
                "browse_active": browse_active,
                "dl_active": dl_active,
                "ocr_active": ocr_active,
                "captcha_state": "ok",
                "captcha_cooldown_remaining": 0,
            })

    def _stats_reporter(self):
        while not self._shutdown.is_set():
            self._emit_snapshot()
            self._shutdown.wait(timeout=2)
