"""
PCT Agent — Patent Cooperation Treaty
Orchestrates sub-agents: Scraper → PDF Extractor → Contact Finder
Accepts Excel upload or WIPO URL, extracts contacts from patent PDFs.
"""
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

from shared.memory import load_memory, save_learning, get_best_strategy
from shared.self_debug import run_with_self_debug
from .scraper import scrape_patent_detail, download_pdf, download_wipo_excel
from .pdf_extractor import extract_contacts_from_pdf
from .tests import tests


AGENT_CONFIG = {
    "name": "PCT Agent",
    "description": (
        "Patent Cooperation Treaty agent. Processes patent Excel sheets — "
        "scrapes WIPO PatentScope, downloads RO/101 or 306 PDFs, "
        "extracts email/phone contacts from each patent entry."
    ),
    "role": "Patent Data Processor",
    "goal": "Extract contact information from WIPO patent filings",
    "status": "active",
    "version": "1.0.0",
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
    "sub_agents": ["Scraper", "PDF Extractor"],
}

STEP_DELAY = 0.3


def find_url_column(headers):
    """Find the column that contains WIPO URLs."""
    url_keywords = ["url", "link", "wipo", "patentscope", "patent_url", "web"]
    for i, h in enumerate(headers):
        if h is None:
            continue
        h_lower = str(h).lower().strip()
        for kw in url_keywords:
            if kw in h_lower:
                return i
    # Fallback: scan first few rows for patentscope URLs
    return None


def find_url_column_by_content(ws, max_scan=5):
    """Scan cell values to find a column containing WIPO URLs."""
    for row in ws.iter_rows(min_row=2, max_row=min(ws.max_row, max_scan + 1)):
        for cell in row:
            if cell.value and "patentscope.wipo.int" in str(cell.value):
                return cell.column - 1  # 0-indexed
    return None


def run_agent(input_data=None, on_step=None):
    """
    Execute the PCT agent.
    input_data expects:
      - file_path: path to uploaded Excel
      - mode: "upload" or "wipo_download"
    """
    start_time = time.time()
    agent_name = "pct_agent"

    # --- Step 1: Load memory ---
    if on_step:
        on_step("Loading PCT agent memory...")
    time.sleep(STEP_DELAY)
    memory = load_memory(agent_name)
    runs = memory["stats"]["total_runs"]
    rate = memory["stats"]["success_rate"]
    if on_step:
        on_step(f"Memory loaded — {runs} past runs, {rate:.0%} success rate")
    time.sleep(STEP_DELAY)

    # --- Step 2: Select strategy ---
    if on_step:
        on_step("Selecting best strategy...")
    strategy = get_best_strategy(agent_name, "process_excel", default="sequential_scrape")
    if on_step:
        on_step(f"Strategy: {strategy}")
    time.sleep(STEP_DELAY)

    # --- Step 3: Validate input ---
    if not input_data:
        input_data = {}

    mode = input_data.get("mode", "upload")
    file_path = input_data.get("file_path")

    if mode == "wipo_download":
        if on_step:
            on_step("[Mode: WIPO Download] Downloading Excel from PatentScope...")
        time.sleep(STEP_DELAY)

        def do_download():
            return download_wipo_excel(on_step=on_step)

        dl_result = run_with_self_debug(do_download, max_retries=2, on_step=on_step)
        if dl_result["status"] == "success" and dl_result["result"]:
            file_path = dl_result["result"]
            if on_step:
                on_step(f"Excel downloaded: {file_path}")
        else:
            if on_step:
                on_step("[WIPO Download] Could not download Excel — check network/URL")
            save_learning(agent_name, "process_excel", "failure",
                          "WIPO download failed", "try_different_headers")
            return {
                "status": "failure",
                "error": "Could not download Excel from WIPO PatentScope",
                "results": [],
                "summary": {"total": 0, "found": 0, "not_found": 0, "errors": 0},
            }

    if not file_path or not os.path.exists(file_path):
        error_msg = f"Excel file not found: {file_path}"
        if on_step:
            on_step(f"ERROR: {error_msg}")
        return {
            "status": "failure",
            "error": error_msg,
            "results": [],
            "summary": {"total": 0, "found": 0, "not_found": 0, "errors": 0},
        }

    # --- Step 4: Check dependencies ---
    if not HAS_OPENPYXL:
        if on_step:
            on_step("ERROR: openpyxl not installed — pip install openpyxl")
        return {
            "status": "failure",
            "error": "openpyxl is required. Install with: pip install openpyxl",
            "results": [],
            "summary": {"total": 0, "found": 0, "not_found": 0, "errors": 0},
        }

    # --- Step 5: Read Excel ---
    if on_step:
        on_step(f"[Excel Reader] Opening: {Path(file_path).name}")
    time.sleep(STEP_DELAY)

    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]

    if on_step:
        on_step(f"[Excel Reader] Found {ws.max_row - 1} rows, {len(headers)} columns")
        on_step(f"[Excel Reader] Headers: {headers}")
    time.sleep(STEP_DELAY)

    # Find URL column
    url_col_idx = find_url_column(headers)
    if url_col_idx is None:
        url_col_idx = find_url_column_by_content(ws)

    if url_col_idx is None:
        if on_step:
            on_step("ERROR: No URL column found in Excel")
        return {
            "status": "failure",
            "error": "Could not find a column with WIPO URLs in the Excel file",
            "results": [],
            "summary": {"total": 0, "found": 0, "not_found": 0, "errors": 0},
        }

    if on_step:
        on_step(f"[Excel Reader] URL column found: '{headers[url_col_idx]}' (column {url_col_idx + 1})")
    time.sleep(STEP_DELAY)

    # --- Step 6: Process each row ---
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })

    results = []
    found_count = 0
    not_found_count = 0
    error_count = 0
    total_rows = ws.max_row - 1

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=1):
        row_data = list(row)
        url = str(row_data[url_col_idx]) if url_col_idx < len(row_data) and row_data[url_col_idx] else None

        if not url or "patentscope" not in url:
            results.append({
                "row": row_idx,
                "url": url,
                "status": "skipped",
                "reason": "No valid WIPO URL",
                "emails": [],
                "phones": [],
            })
            continue

        if on_step:
            on_step(f"[Row {row_idx}/{total_rows}] Processing: {url[:80]}...")

        # Extract docId for naming
        doc_id_match = re.search(r'docId=(\w+)', url)
        doc_id = doc_id_match.group(1) if doc_id_match else f"row_{row_idx}"

        # Step 6a: Find PDF URL on the patent detail page
        if on_step:
            on_step(f"[Row {row_idx}] [Scraper] Searching for RO/101 or 306 PDF...")

        pdf_url = scrape_patent_detail(url, session=session, on_step=on_step)

        if not pdf_url:
            if on_step:
                on_step(f"[Row {row_idx}] [Scraper] No PDF found — marking as not_found")
            results.append({
                "row": row_idx,
                "url": url,
                "doc_id": doc_id,
                "status": "not_found",
                "reason": "No RO/101 or 306 PDF found on detail page",
                "emails": [],
                "phones": [],
            })
            not_found_count += 1
            continue

        # Step 6b: Download the PDF
        if on_step:
            on_step(f"[Row {row_idx}] [Scraper] Downloading PDF...")

        pdf_path = download_pdf(pdf_url, doc_id, session=session, on_step=on_step)

        if not pdf_path:
            results.append({
                "row": row_idx,
                "url": url,
                "doc_id": doc_id,
                "status": "error",
                "reason": "PDF download failed",
                "emails": [],
                "phones": [],
            })
            error_count += 1
            continue

        # Step 6c: Extract contacts from PDF
        if on_step:
            on_step(f"[Row {row_idx}] [PDF Extractor] Extracting contacts...")

        contacts = extract_contacts_from_pdf(pdf_path, on_step=on_step)

        row_result = {
            "row": row_idx,
            "url": url,
            "doc_id": doc_id,
            "status": contacts["status"],
            "emails": contacts.get("emails", []),
            "phones": contacts.get("phones", []),
        }

        if contacts["status"] == "found":
            found_count += 1
            if on_step:
                on_step(
                    f"[Row {row_idx}] FOUND: "
                    f"{', '.join(contacts['emails'][:2])} | "
                    f"{', '.join(contacts['phones'][:2])}"
                )
        elif contacts["status"] == "not_found":
            not_found_count += 1
            if on_step:
                on_step(f"[Row {row_idx}] No contact info found in PDF")
        else:
            error_count += 1
            row_result["reason"] = contacts.get("error", "Unknown error")
            if on_step:
                on_step(f"[Row {row_idx}] Error: {contacts.get('error', 'Unknown')}")

        results.append(row_result)

        # Small delay between requests to avoid rate limiting
        time.sleep(0.5)

    # --- Step 7: Generate output Excel ---
    if on_step:
        on_step(f"[Output] Generating output Excel...")
    time.sleep(STEP_DELAY)

    output_path = generate_output_excel(file_path, headers, results, on_step)

    if on_step:
        on_step(f"[Output] Saved: {Path(output_path).name}")
    time.sleep(STEP_DELAY)

    # --- Step 8: Self-test ---
    if on_step:
        on_step("Running self-tests...")
    time.sleep(STEP_DELAY)

    agent_result = {
        "status": "success",
        "results": results,
        "summary": {
            "total": total_rows,
            "processed": len(results),
            "found": found_count,
            "not_found": not_found_count,
            "errors": error_count,
            "skipped": len([r for r in results if r["status"] == "skipped"]),
        },
        "output_file": output_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    test_result = tests.run(agent_result)
    agent_result["tests"] = test_result

    if on_step:
        if test_result["passed"]:
            on_step(f"All {test_result['total']} self-tests passed!")
        else:
            on_step(f"Self-tests: {test_result['passed_count']}/{test_result['total']} passed")

    # --- Step 9: Save learning ---
    execution_time = time.time() - start_time
    insight = (
        f"Processed {total_rows} rows: {found_count} contacts found, "
        f"{not_found_count} not found, {error_count} errors"
    )
    save_learning(
        agent_name, "process_excel",
        "success" if found_count > 0 or not_found_count > 0 else "partial",
        insight, strategy, execution_time,
    )

    if on_step:
        on_step(f"Learning saved. Total time: {execution_time:.1f}s")
    time.sleep(STEP_DELAY)

    if on_step:
        on_step(
            f"DONE — {found_count} contacts found, {not_found_count} not found, "
            f"{error_count} errors out of {total_rows} rows"
        )

    agent_result["execution_time"] = round(execution_time, 2)
    agent_result["attempts"] = 1
    return agent_result


def generate_output_excel(original_path, original_headers, results, on_step=None):
    """Generate output Excel with original data + new contact columns."""
    wb_in = openpyxl.load_workbook(original_path, data_only=True)
    ws_in = wb_in.active

    wb_out = openpyxl.Workbook()
    ws_out = wb_out.active
    ws_out.title = "PCT Results"

    # Write headers: original + new contact columns
    out_headers = list(original_headers) + ["Email(s)", "Phone(s)", "Contact Status"]
    for col_idx, h in enumerate(out_headers, start=1):
        ws_out.cell(row=1, column=col_idx, value=h)

    # Build results lookup by row number
    results_map = {r["row"]: r for r in results}

    # Copy data rows and append contact info
    for row_idx, row in enumerate(ws_in.iter_rows(min_row=2, values_only=True), start=1):
        out_row = list(row)
        result = results_map.get(row_idx, {})

        emails = "; ".join(result.get("emails", []))
        phones = "; ".join(result.get("phones", []))
        status = result.get("status", "skipped")

        out_row.extend([emails, phones, status])

        for col_idx, val in enumerate(out_row, start=1):
            ws_out.cell(row=row_idx + 1, column=col_idx, value=val)

    # Save output
    output_dir = Path(original_path).parent.parent / "outputs"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_name = f"pct_results_{timestamp}.xlsx"
    output_path = output_dir / output_name
    wb_out.save(str(output_path))

    wb_in.close()
    return str(output_path)
