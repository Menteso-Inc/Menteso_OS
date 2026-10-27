"""Opt-in local inference contract check using a synthetic filing, never WIPO.

This is not an accuracy benchmark. Reserved test addresses bypass DNS only in
this isolated process; the production configuration and source sheets are not read.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--live-root', type=Path, required=True)
    args = parser.parse_args()
    from check_pct_activation import check
    if not check(args.live_root)['ready_for_maintenance']:
        raise SystemExit('Local PCT is busy; defer this CPU inference check.')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update({'PCT_AI_PROVIDER': 'ollama', 'PCT_AI_VERIFY_ENABLED': 'true',
                       'PCT_AI_EVIDENCE_DIR': str(output / 'evidence'),
                       'PCT_EMAIL_DNS_CHECK': 'false', 'PCT_EMAIL_ENABLED': 'false'})
    import fitz
    from agents.pct_agent import ai_verifier as ai, agent
    ai.validate_configuration(check_api=True)
    path = output / 'synthetic-filing.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=220, height=110)
        page.insert_text((12, 22), 'IV-1 Agent / representative\nName: Example Counsel LLP\nEmail: docket@example.org', fontsize=10)
        doc.save(path)
    started = time.monotonic()
    result = ai.verify_contacts(path, {}, on_step=lambda text: print(text, flush=True),
                                context={'id': 'SYNTHETIC-CONTRACT-CHECK'})
    elapsed = round(time.monotonic() - started, 2)
    evidence = Path(result.get('evidence_file', ''))
    record = json.loads(evidence.read_text(encoding='utf-8')) if evidence.suffix == '.json' else {}
    checks = {'status_found': result.get('status') == 'found',
              'exact_synthetic_email': result.get('emails') == ['docket@example.org'],
              'both_required_readings': bool(record.get('visual_extraction') and record.get('second_reading')),
              'local_provider_recorded': record.get('provider') == 'ollama'}
    agent.PCT_OUTPUT_DIR = output / 'reports'
    agent.PCT_OUTPUT_DIR.mkdir()
    row = {'row': 1, 'patent_id': 'SYNTHETIC-CONTRACT-CHECK', 'title': 'Synthetic test only',
           'appl_no': 'TEST', 'applicant': 'Source applicant', **result}
    paths = agent.write_pct_reports([row])
    import openpyxl
    for sheet_path in paths:
        book = openpyxl.load_workbook(sheet_path)
        try:
            checks[Path(sheet_path).name + '_headers'] = [cell.value for cell in book.active[1]] == agent.WORK_REPORT_HEADERS
        finally:
            book.close()
    report = {'scope': 'Synthetic provider/schema/two-reading/workbook check; not source accuracy or production throughput',
              'model': ai.model_name(), 'seconds': elapsed, 'checks': checks,
              'passed': all(checks.values()), 'dns_disabled_only_for_reserved_synthetic_addresses': True,
              'evidence_file': result.get('evidence_file'), 'error': result.get('error'),
              'reports': [str(path) for path in paths]}
    (output / 'contract-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
