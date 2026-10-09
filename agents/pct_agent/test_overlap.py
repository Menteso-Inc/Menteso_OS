"""Concurrency must preserve source rows, verification and workbook contents."""
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

from agents.pct_agent import agent, ai_verifier as ai, overlap
from agents.pct_agent import resume
from agents.pct_agent.test_ai_verifier import extraction, field


def source_rows(count=3):
    return [dict(id=f"WO/2026/{index:06}", title=f"Title {index}",
                 appl_no=f"US2026/{index}", applicant=f"Applicant {index}",
                 researcher="Aneeq", priority_date="Original date")
            for index in range(1, count + 1)]


def contacts(index):
    return {"status": "found", "emails": [f"row.{index}+patent@example.org"],
            "phones": [f"+1 212 555 {index:04}"], "name": f"Owner {index}",
            "agent_name": f"Agent {index}", "country": "US", "category": "Slf",
            "ai_status": "verified", "contact_owner": f"Owner {index}",
            "contact_role": "agent", "verification_revision": "test-revision"}


def make_result(row, url, contact):
    result = agent._row_result(row["_row_idx"], row, url, "", contact["status"],
                               emails=contact.get("emails"), phones=contact.get("phones"),
                               name=contact.get("name", ""), reason=contact.get("reason", ""))
    result.update(ai.result_metadata(contact))
    return result


class FakeBrowser:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.closed = False
        self.owner = threading.get_ident()
        self.last_failure_reason = ""

    def start(self):
        assert threading.get_ident() == self.owner

    def scrape_patent(self, url, doc_id, on_step=None):
        assert threading.get_ident() == self.owner
        self.calls.append((url, doc_id))
        return doc_id + ".pdf"

    def force_stop(self):
        pass

    def close(self):
        assert threading.get_ident() == self.owner
        self.closed = True


def test_independent_reads_overlap_and_retain_identity(monkeypatch):
    both_started = threading.Barrier(2)
    second_done = threading.Event()
    first_pages = [(2, b"contact image"), (1, b"cover image")]
    second_answer = extraction(field("second@example.org"))
    first_answer = extraction(field("first@example.org"))

    def request(pages, rules, context):
        assert context == {"id": "WO1"}
        both_started.wait(timeout=3)
        if pages[0][0] == 1:
            second_done.set()
            return second_answer
        assert second_done.wait(3)
        return first_answer

    monkeypatch.setattr(ai, "_request", request)
    first, second = ai._read_original_pages(first_pages, ai.load_rules(), {"id": "WO1"})
    assert first is first_answer and second is second_answer


def test_second_read_failure_does_not_return_first_read(monkeypatch):
    def request(pages, *args):
        if pages[0][0] == 1:
            raise RuntimeError("openai_http_429")
        return extraction(field())
    monkeypatch.setattr(ai, "_request", request)
    with pytest.raises(RuntimeError, match="openai_http_429"):
        ai._read_original_pages([(2, b"a"), (1, b"b")], ai.load_rules(), {})


def test_api_concurrency_never_exceeds_existing_two_request_limit(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    lock = threading.Lock()
    activity = {"active": 0, "maximum": 0, "calls": 0}
    def post(*args, **kwargs):
        with lock:
            activity["active"] += 1
            activity["maximum"] = max(activity["maximum"], activity["active"])
            activity["calls"] += 1
        time.sleep(0.03)
        with lock:
            activity["active"] -= 1
        return SimpleNamespace(status_code=200, json=lambda: {
            "status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": extraction(field()).model_dump_json()}
            ]}]
        })
    monkeypatch.setenv("PCT_OPENAI_API_KEY", "offline-test-placeholder")
    monkeypatch.setattr(ai.requests, "post", post)
    with ThreadPoolExecutor(max_workers=2) as callers:
        futures = [callers.submit(ai._read_original_pages, [(1, b"a")], ai.load_rules(), {}) for _ in range(2)]
        for future in futures:
            assert len(future.result()) == 2
    assert activity == {"active": 0, "maximum": 2, "calls": 4}


def test_download_and_verification_overlap_without_crossing_rows():
    rows = source_rows()
    # Repeated patent IDs must still produce distinct files and output rows.
    rows[1]["id"] = rows[0]["id"]
    browser = FakeBrowser()
    second_download = threading.Event()
    publications = []
    writer_thread = threading.get_ident()
    original_scrape = browser.scrape_patent

    def scrape(url, doc_id, **kwargs):
        path = original_scrape(url, doc_id, **kwargs)
        if len(browser.calls) == 2:
            second_download.set()
        return path
    browser.scrape_patent = scrape

    def verify(path, on_step, context):
        assert threading.get_ident() != writer_thread
        index = context["_row_idx"]
        assert f"row{index}.pdf" in path
        if index == 1:
            assert second_download.wait(3), "Downloader blocked on first verification"
        return contacts(index)

    def record(result):
        assert threading.get_ident() == writer_thread
        publications.append(result)

    results = overlap.process_rows(rows, browser, verify, make_result, record,
                                   lambda _: None, lambda _: None, lambda: False,
                                   "test-run", min_interval=0)
    assert [r["row"] for r in results] == [1, 2, 3]
    assert [r["emails"] for r in results] == [[f"row.{i}+patent@example.org"] for i in (1, 2, 3)]
    assert len({doc_id for _, doc_id in browser.calls}) == 3
    assert len(publications) == 3
    assert all("_row_idx" not in row for row in rows), "Input records were mutated"


def test_stop_drains_downloaded_rows_without_starting_more():
    stopped = threading.Event()
    two_downloaded = threading.Event()
    browser = FakeBrowser()
    original_scrape = browser.scrape_patent

    def scrape(*args, **kwargs):
        path = original_scrape(*args, **kwargs)
        if len(browser.calls) == 2:
            stopped.set()
            two_downloaded.set()
        return path
    browser.scrape_patent = scrape

    def verify(path, on_step, context):
        assert two_downloaded.wait(3)
        return contacts(context["_row_idx"])

    results = overlap.process_rows(source_rows(10), browser, verify, make_result,
                                   lambda _: None, lambda _: None, lambda _: None,
                                   stopped.is_set, "stop-test", min_interval=0)
    assert len(browser.calls) == 2
    assert [r["row"] for r in results] == [1, 2]


@pytest.mark.parametrize("reason,expected,attempts", [
    ("nav_failed", "error", 2), ("download_failed", "error", 2),
    ("pdf_lookup_unconfirmed", "error", 2), ("no_pdf_row", "not_found", 1),
])
def test_failed_downloads_are_retried_and_never_reported_as_missing_contacts(monkeypatch, reason, expected, attempts):
    clock = [0.0]
    monkeypatch.setattr(overlap, "time", SimpleNamespace(
        monotonic=lambda: clock[0], sleep=lambda duration: clock.__setitem__(0, clock[0] + duration)))
    browser = FakeBrowser()
    def scrape(url, doc_id, **kwargs):
        browser.calls.append((url, doc_id))
        browser.last_failure_reason = reason
        return None
    browser.scrape_patent = scrape
    def no_verification(*args, **kwargs):
        pytest.fail("Verification called without a PDF")
    results = overlap.process_rows(source_rows(1), browser, no_verification, make_result,
                                   lambda _: None, lambda _: None, lambda _: None,
                                   lambda: False, "failure-test", min_interval=0)
    assert results[0]["status"] == expected and results[0]["reason"] == reason
    assert len(browser.calls) == attempts


def workbook_contents(path):
    workbook = openpyxl.load_workbook(path)
    sheet = workbook.active
    contents = {
        "title": sheet.title,
        "values": list(sheet.values),
        "styles": [[(cell.font.bold, cell.number_format, cell.data_type) for cell in row] for row in sheet],
        "columns": {key: value.width for key, value in sheet.column_dimensions.items()},
        "freeze_panes": sheet.freeze_panes,
        "auto_filter": sheet.auto_filter.ref,
    }
    workbook.close()
    return contents


def test_full_sheet_preserves_format_values_order_and_checkpoints(tmp_path, monkeypatch):
    rows = source_rows(30)
    monkeypatch.setattr(agent, "PCT_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(agent, "PatentBrowser", FakeBrowser)
    monkeypatch.setattr(agent, "save_learning", lambda *args: None)
    # Pacing is tested separately; eliminate wall-clock waits here.
    monkeypatch.setattr(overlap, "bounded_setting", lambda name, default, *args: 0 if "INTERVAL" in name else default)
    monkeypatch.setattr(agent, "extract_contacts_from_pdf",
                        lambda path, on_step, context: contacts(context["_row_idx"]))
    events = []
    result = agent._run_chunked_sequential_mode(
        rows, "input.xlsx", "pct_agent", "default", time.time(), lambda _: None, events.append,
        live_level_getter=lambda: 5,
    )
    assert result["status"] == "success" and result["tests"]["passed"]
    assert result["summary"] == {"total": 30, "processed": 30, "found": 30, "not_found": 0, "errors": 0}
    assert len(list(tmp_path.glob("*.xlsx"))) == 2, "Checkpoints created extra workbooks"
    journal = [json.loads(line) for line in Path(result["progress_file"]).read_text().splitlines()]
    assert len(journal) == 31 and journal[0]["_meta"]
    assert [r["row"] for r in journal[1:]] == list(range(1, 31))
    expected_rows = [make_result({**row, "_row_idx": i}, agent.id_to_url(row["id"]), contacts(i))
                     for i, row in enumerate(rows, 1)]
    reference_dir = tmp_path / "reference"
    monkeypatch.setattr(agent, "PCT_OUTPUT_DIR", reference_dir)
    expected_worked, expected_missed = agent.write_pct_reports(expected_rows)
    assert workbook_contents(result["output_file"]) == workbook_contents(expected_worked)
    assert workbook_contents(result["not_found_file"]) == workbook_contents(expected_missed)
    assert workbook_contents(result["output_file"])["values"][0] == tuple(agent.WORK_REPORT_HEADERS)
    assert len([e for e in events if e["event"] == "contacts"]) == 30


def test_report_replace_failure_preserves_previous_workbook(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "PCT_OUTPUT_DIR", tmp_path)
    path = Path(agent.generate_work_report([]))
    original = path.read_bytes()
    def locked(*args):
        raise PermissionError("open in Excel")
    monkeypatch.setattr(agent.os, "replace", locked)
    with pytest.raises(PermissionError):
        agent.generate_work_report([{"row": 1, "patent_id": "WO1"}], target_path=path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp.xlsx"))


def test_verification_exception_preserves_row_as_error():
    def fail(*args, **kwargs):
        raise RuntimeError("API failure")
    results = overlap.process_rows(source_rows(1), FakeBrowser(), fail, make_result,
                                   lambda _: None, lambda _: None, lambda _: None,
                                   lambda: False, "verification-error", min_interval=0)
    assert results[0]["status"] == "error" and results[0]["row"] == 1
    assert results[0]["emails"] == []


def test_checkpoint_failure_cannot_report_success(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "PCT_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(agent, "PatentBrowser", FakeBrowser)
    monkeypatch.setattr(agent, "save_learning", lambda *args: None)
    monkeypatch.setattr(agent, "extract_contacts_from_pdf",
                        lambda path, on_step, context: contacts(context["_row_idx"]))
    def failed_report(*args, **kwargs):
        raise PermissionError("workbook locked")
    monkeypatch.setattr(agent, "write_pct_reports", failed_report)
    result = agent._run_chunked_sequential_mode(
        source_rows(1), "input.xlsx", "pct_agent", "default", time.time(), lambda _: None, lambda _: None)
    assert result["status"] == "partial" and "report_write_failed" in result["error"]
    assert result["summary"]["processed"] == 1
    assert len(Path(result["progress_file"]).read_text().splitlines()) == 2


def test_upload_entry_point_uses_single_browser_and_preserves_source_cells(tmp_path, monkeypatch):
    source = tmp_path / "input.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.append(["Publication No", "Title", "Application No", "Applicant", "Researcher", "Priorty Date"])
    workbook.active.append(["WO/2026/001", "Original title", "US2026/001", "Original Applicant Ltd.", "Aneeq", "Original date"])
    workbook.save(source)
    workbook.close()
    browsers = []
    def create_browser(**kwargs):
        browser = FakeBrowser(**kwargs)
        browsers.append(browser)
        return browser
    monkeypatch.setattr(agent, "PCT_OUTPUT_DIR", tmp_path / "reports")
    monkeypatch.setattr(agent, "PCT_INPUT_ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr(agent, "PatentBrowser", create_browser)
    monkeypatch.setattr(agent, "validate_configuration", lambda **kwargs: None)
    monkeypatch.setattr(agent, "load_memory", lambda _: {"stats": {"total_runs": 0, "success_rate": 0}})
    monkeypatch.setattr(agent, "get_best_strategy", lambda *args, **kwargs: "default")
    monkeypatch.setattr(agent, "save_learning", lambda *args: None)
    monkeypatch.setattr(agent, "extract_contacts_from_pdf",
                        lambda path, on_step, context: contacts(context["_row_idx"]))
    def forbidden(*args, **kwargs):
        pytest.fail("Legacy fast mode must not run")
    monkeypatch.setattr(agent, "_run_pipeline_mode", forbidden)
    result = agent.run_agent({"file_path": str(source), "mode": "upload", "fast_level": 5,
                              "get_live_fast_level": lambda: 5})
    assert result["status"] == "success" and result["tests"]["passed"]
    assert len(browsers) == 1 and browsers[0].closed
    cells = workbook_contents(result["output_file"])["values"][1]
    assert cells[:4] == ("WO/2026/001", "Original title", "US2026/001", "Original Applicant Ltd.")
    assert cells[10:] == ("Aneeq", "Original date")


def handoff_fixture(tmp_path, rows, saved):
    source = tmp_path / "source.xls"
    source.write_bytes(b"original-sheet-bytes")
    path = tmp_path / "handoff.json"
    data = {"version": 1, "input_sha256": resume.file_hash(source), "total": len(rows),
            "policy_fingerprint": resume.policy_fingerprint(), "results": saved}
    path.write_text(json.dumps(data), encoding="utf-8")
    return source, path, data


def test_resume_policy_fingerprint_ignores_platform_line_endings(tmp_path, monkeypatch):
    original = resume.policy_fingerprint()
    contents = Path(resume.policy.__file__).read_text(encoding="utf-8")
    path = tmp_path / "policy.py"
    path.write_bytes(contents.replace("\n", "\r\n").encode("utf-8"))
    monkeypatch.setattr(resume.policy, "__file__", str(path))
    assert resume.policy_fingerprint() == original


def test_resume_retains_saved_rows_and_only_downloads_unfinished_rows(tmp_path, monkeypatch):
    rows = source_rows(6)
    saved = [make_result({**rows[i - 1], "_row_idx": i}, agent.id_to_url(rows[i - 1]["id"]), contacts(i))
             for i in (1, 2, 4)]
    # Preserve completed errors too; gaps still resume at their original index.
    saved[1].update(status="error", emails=[], phones=[], reason="previous_error")
    source, path, _ = handoff_fixture(tmp_path, rows, saved)
    loaded = resume.load_handoff(path, source, rows)
    browser = FakeBrowser()
    monkeypatch.setattr(agent, "PatentBrowser", lambda **kwargs: browser)
    monkeypatch.setattr(agent, "PCT_OUTPUT_DIR", tmp_path / "reports")
    monkeypatch.setattr(agent, "save_learning", lambda *args: None)
    monkeypatch.setattr(overlap, "bounded_setting", lambda name, default, *args: 0 if "INTERVAL" in name else default)
    monkeypatch.setattr(agent, "extract_contacts_from_pdf",
                        lambda path, on_step, context: contacts(context["_row_idx"]))
    events, steps = [], []
    result = agent._run_chunked_sequential_mode(
        rows, str(source), "pct_agent", "default", time.time(), steps.append, events.append,
        resumed_results=loaded)
    assert result["status"] == "success" and result["resumed_rows"] == 3
    assert result["summary"] == {"total": 6, "processed": 6, "found": 5, "not_found": 0, "errors": 1}
    assert [e["row"] for e in events if e["event"] == "navigate"] == [3, 5, 6]
    assert len(browser.calls) == 3
    assert [r["row"] for r in result["results"]] == list(range(1, 7))
    assert result["results"][1]["reason"] == "previous_error"
    assert result["results"][0]["emails"] == saved[0]["emails"]
    assert any(isinstance(s, dict) and s.get("found") == 2 and s.get("errors") == 1 for s in steps)
    timing = events[-1]["timing"]
    assert timing["resumedRows"] == 3 and len(timing["rowTimestamps"]) == 3
    assert len(Path(result["progress_file"]).read_text().splitlines()) == 7
    values = workbook_contents(result["output_file"])["values"]
    assert values[0] == tuple(agent.WORK_REPORT_HEADERS) and len(values) == 6
    assert [row[0] for row in values[1:]] == [rows[i - 1]["id"] for i in (1, 3, 4, 5, 6)]


@pytest.mark.parametrize("corruption", ["input", "policy", "total", "duplicate", "source", "index", "unfinished"])
def test_resume_rejects_mismatched_or_corrupt_handoff(tmp_path, corruption):
    rows = source_rows(2)
    saved = [make_result({**rows[0], "_row_idx": 1}, agent.id_to_url(rows[0]["id"]), contacts(1))]
    source, path, data = handoff_fixture(tmp_path, rows, saved)
    if corruption == "input": source.write_bytes(b"different input")
    elif corruption == "policy": data["policy_fingerprint"] = "different rules"
    elif corruption == "total": data["total"] = 3
    elif corruption == "duplicate": data["results"].append(dict(saved[0]))
    elif corruption == "source": data["results"][0]["applicant"] = "Wrong applicant"
    elif corruption == "index": data["results"][0]["row"] = 0
    elif corruption == "unfinished": data["results"][0]["status"] = "processing"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        resume.load_handoff(path, source, rows)
