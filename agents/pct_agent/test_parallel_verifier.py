"""Real Windows-spawn workers, offline AI, and checkpoint/output invariants."""
import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from agents.pct_agent import agent, overlap, parallel_verifier
from agents.pct_agent.test_overlap import source_rows, contacts, make_result, FakeBrowser, workbook_contents


def offline_verify(path, on_step, context):
    """Runs the real PDF verifier with deterministic HTTP responses, never the API."""
    from agents.pct_agent import ai_verifier as ai
    from agents.pct_agent.pdf_extractor import extract_contacts_from_pdf
    from agents.pct_agent.test_ai_verifier import extraction, field
    index = context['_row_idx']
    base = Path(os.environ['PCT_PARALLEL_TEST_DIR'])
    (base / f'start-{index}').write_text(str(os.getpid()))
    deadline = time.monotonic() + 20
    while len(list(base.glob('start-*'))) < 4:
        if time.monotonic() > deadline:
            raise RuntimeError('Four PDF workers did not start together')
        time.sleep(.02)
    calls = []
    lock = threading.Lock()
    def post(*args, **kwargs):
        with lock:
            call = len(calls)
            calls.append(kwargs['json'])
        start = time.monotonic()
        time.sleep(.15)
        end = time.monotonic()
        (base / f'api-{index}-{call}.json').write_text(json.dumps([start, end]))
        return SimpleNamespace(status_code=200, json=lambda: {
            'status': 'completed', 'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': extraction(field(f'row{index}@example.org')).model_dump_json()}
            ]}]
        })
    ai.requests.post = post
    ai._high_res_ocr_emails = lambda *args: []
    ai.policy.email_domain_status = lambda *args: 'mx'
    result = extract_contacts_from_pdf(path, on_step=on_step, context=context)
    assert len(calls) == 2, 'Both original image readings must run'
    assert calls[0]['model'] == calls[1]['model'] == 'gpt-4o'
    if index == 1:
        time.sleep(.7)  # Force completion order to differ from source order.
    return result


def failing_verify(path, on_step, context):
    if context['_row_idx'] == 2:
        raise RuntimeError('Offline worker failure')
    return contacts(context['_row_idx'])


def test_spawned_verifiers_keep_both_reads_and_share_api_bound(tmp_path, monkeypatch):
    monkeypatch.setenv('PCT_PARALLEL_TEST_DIR', str(tmp_path))
    monkeypatch.setenv('PCT_AI_EVIDENCE_DIR', str(tmp_path / 'evidence'))
    monkeypatch.setenv('PCT_OPENAI_API_KEY', 'offline-test-placeholder')
    monkeypatch.setenv('PCT_AI_MODEL', 'gpt-4o')
    with parallel_verifier.ProcessVerifier(4, 3, offline_verify) as pool:
        futures = []
        for index, row in enumerate(source_rows(4), 1):
            path = tmp_path / f'row{index}.pdf'
            with fitz.open() as document:
                page = document.new_page()
                page.insert_text((50, 60), f'Agent: John Lee\nEmail: row{index}@example.org', fontsize=16)
                document.save(path)
            futures.append(pool.submit(path, {**row, '_row_idx': index}))
        results = [future.result(timeout=40) for future in futures]
        messages = list(pool.drain_messages())
    assert len({p.read_text() for p in tmp_path.glob('start-*')}) == 4
    for index, result in enumerate(results, 1):
        assert result['status'] == 'found'
        assert result['emails'] == [f'row{index}@example.org']
        record = json.loads(Path(result['evidence_file']).read_text())
        assert record['visual_extraction'] and record['second_reading']
    transitions = []
    for path in tmp_path.glob('api-*.json'):
        start, end = json.loads(path.read_text())
        transitions.extend([(start, 1), (end, -1)])
    active = peak = 0
    for _, delta in sorted(transitions):
        active += delta
        peak = max(peak, active)
    assert len(transitions) == 16 and 1 < peak <= 3
    assert any('[Timing]' in message for message in messages)


@pytest.mark.parametrize('stop_after_four', [False, True])
def test_parallel_stop_resume_and_worker_error_preserve_rows(tmp_path, monkeypatch, stop_after_four):
    real_pool = parallel_verifier.ProcessVerifier
    monkeypatch.setattr(parallel_verifier, 'ProcessVerifier',
                        lambda workers, slots: real_pool(workers, slots, failing_verify))
    browser = FakeBrowser()
    stop = threading.Event()
    original_scrape = browser.scrape_patent
    def scrape(*args, **kwargs):
        path = original_scrape(*args, **kwargs)
        if stop_after_four and len(browser.calls) == 4:
            stop.set()
        return path
    browser.scrape_patent = scrape
    writer = threading.get_ident()
    journal = overlap.RowJournal(tmp_path / 'progress.jsonl', 'input.xls', 9)
    def record(result):
        assert threading.get_ident() == writer
        journal.append(result)
    saved = {1, 3}
    results = overlap.process_rows(source_rows(9), browser, None, make_result, record,
                                   lambda _: None, lambda _: None, stop.is_set, 'parallel-test',
                                   max_pending=4, min_interval=0, completed_rows=saved,
                                   verification_workers=4, api_concurrency=3)
    expected = [2, 4, 5, 6] if stop_after_four else [2, 4, 5, 6, 7, 8, 9]
    assert [r['row'] for r in results] == expected
    assert len(browser.calls) == len(expected)
    assert results[0]['status'] == 'error' and results[0]['reason'].startswith('verification_exception:')
    assert all(r['status'] == 'found' for r in results[1:])
    entries = [json.loads(line) for line in journal.path.read_text().splitlines()][1:]
    assert sorted(r['row'] for r in entries) == expected


def test_parallel_agent_rebuilds_ordered_sheets_with_retained_contacts(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    class OfflinePool:
        def __init__(self, *args): self.pool = ThreadPoolExecutor(max_workers=4)
        def __enter__(self): return self
        def __exit__(self, *args): self.pool.shutdown()
        def drain_messages(self): return []
        def submit(self, path, row):
            def verify():
                if row['_row_idx'] == 2: time.sleep(.15)
                return contacts(row['_row_idx'])
            return self.pool.submit(verify)
    monkeypatch.setattr(parallel_verifier, 'ProcessVerifier', OfflinePool)
    monkeypatch.setattr(agent, 'PCT_OUTPUT_DIR', tmp_path / 'reports')
    monkeypatch.setattr(agent, 'PatentBrowser', FakeBrowser)
    monkeypatch.setattr(agent, 'save_learning', lambda *args: None)
    monkeypatch.setattr(overlap, 'bounded_setting',
                        lambda name, default, *args: 0 if 'INTERVAL' in name else 4 if name == 'PCT_PDF_VERIFICATION_WORKERS' else default)
    rows = source_rows(8)
    retained = make_result({**rows[0], '_row_idx': 1}, agent.id_to_url(rows[0]['id']), contacts(1))
    result = agent._run_chunked_sequential_mode(rows, 'input.xls', 'pct_agent', 'default',
                                               time.time(), lambda _: None, lambda _: None,
                                               resumed_results=[retained.copy()])
    assert result['status'] == 'success' and result['resumed_rows'] == 1
    assert result['results'][0] == retained
    assert [r['row'] for r in result['results']] == list(range(1, 9))
    values = workbook_contents(result['output_file'])['values']
    assert values[0] == tuple(agent.WORK_REPORT_HEADERS)
    assert [r[0] for r in values[1:]] == [r['id'] for r in rows]


def test_excel_invalid_controls_do_not_block_export_or_mutate_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, 'PCT_OUTPUT_DIR', tmp_path)
    rows = source_rows(2)
    found = make_result({**rows[0], '_row_idx': 1}, agent.id_to_url(rows[0]['id']), contacts(1))
    found['phones'] = ['+1\x02 212 555 0100']
    found['title'] = 'Original\tTitle\nsecond line'
    missing = make_result({**rows[1], '_row_idx': 2}, agent.id_to_url(rows[1]['id']),
                          {'status': 'error', 'reason': 'download_failed'})
    missing['applicant'] = 'Example\x0b Company'
    worked, missed = agent.write_pct_reports([found, missing])
    assert workbook_contents(worked)['values'][1][6] == '+1 212 555 0100'
    assert workbook_contents(worked)['values'][1][1] == found['title']
    assert workbook_contents(missed)['values'][1][3] == 'Example Company'
    assert found['phones'] == ['+1\x02 212 555 0100']
    assert missing['applicant'] == 'Example\x0b Company'
