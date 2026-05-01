"""
PCT Agent — Patent Cooperation Treaty
Reads WIPO resultList.xls → scrapes patent pages → extracts contacts → outputs Work Report Excel.

Input:  resultList.xls (from WIPO PatentScope weekly browse) or .xlsx with same columns
Output: Work Report DD-Month-YYYY.xlsx matching the standard work report format
"""
import os
import re
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
from .browser import PatentBrowser
from .pdf_extractor import extract_contacts_from_pdf
from .pipeline import PipelinePCT, ProgressFile
from .tests import tests

# Pipeline config
PIPELINE_THRESHOLD = 50     # rows >= this use parallel pipeline
DEFAULT_BROWSER_WORKERS = 20
DEFAULT_DOWNLOAD_WORKERS = 30
DEFAULT_OCR_WORKERS = 8

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
    "sub_agents": ["Scraper", "PDF Extractor"],
}

STEP_DELAY = 0.3


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


def _read_xls(file_path, on_step=None):
    """Read .xls file using xlrd (WIPO resultList format)."""
    wb = xlrd.open_workbook(file_path)
    ws = wb.sheet_by_index(0)

    if on_step:
        on_step(f"[Excel Reader] Sheet: '{ws.name}' — {ws.nrows} rows x {ws.ncols} cols")

    # Find header row — look for a row where first cell is "ID"
    header_row = None
    for r in range(min(10, ws.nrows)):
        val = str(ws.cell_value(r, 0)).strip()
        if val.upper() == "ID":
            header_row = r
            break

    if header_row is None:
        raise ValueError("Could not find header row with 'ID' column in the Excel file")

    headers = [str(ws.cell_value(header_row, c)).strip() for c in range(ws.ncols)]
    if on_step:
        on_step(f"[Excel Reader] Headers found at row {header_row + 1}: {headers}")

    col_map = _map_columns(headers)

    rows = []
    for r in range(header_row + 1, ws.nrows):
        row_vals = [ws.cell_value(r, c) for c in range(ws.ncols)]
        patent_id = str(row_vals[col_map.get("id", 0)]).strip()
        if not patent_id:
            continue

        rows.append({
            "id": patent_id,
            "title": str(row_vals[col_map.get("title", 1)]).strip(),
            "appl_no": str(row_vals[col_map.get("appl_no", 3)]).strip(),
            "applicant": str(row_vals[col_map.get("applicant", 5)]).strip(),
            "kind": str(row_vals[col_map.get("kind", 2)]).strip() if "kind" in col_map else "",
            "ipc": str(row_vals[col_map.get("ipc", 4)]).strip() if "ipc" in col_map else "",
        })

    if on_step:
        on_step(f"[Excel Reader] Parsed {len(rows)} patent entries")

    return rows


def _read_xlsx(file_path, on_step=None):
    """Read .xlsx file using openpyxl."""
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active

    if on_step:
        on_step(f"[Excel Reader] Sheet: '{ws.title}' — {ws.max_row} rows x {ws.max_column} cols")

    # Find header row
    header_row = None
    for row in ws.iter_rows(min_row=1, max_row=10, values_only=False):
        for cell in row:
            if cell.value and str(cell.value).strip().upper() == "ID":
                header_row = cell.row
                break
        if header_row:
            break

    if header_row is None:
        raise ValueError("Could not find header row with 'ID' column in the Excel file")

    header_cells = list(ws.iter_rows(min_row=header_row, max_row=header_row))[0]
    headers = [str(cell.value or "").strip() for cell in header_cells]
    if on_step:
        on_step(f"[Excel Reader] Headers found at row {header_row}: {headers}")

    col_map = _map_columns(headers)

    rows = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        row_vals = list(row)
        patent_id = str(row_vals[col_map.get("id", 0)] or "").strip()
        if not patent_id:
            continue

        rows.append({
            "id": patent_id,
            "title": str(row_vals[col_map.get("title", 1)] or "").strip(),
            "appl_no": str(row_vals[col_map.get("appl_no", 3)] or "").strip(),
            "applicant": str(row_vals[col_map.get("applicant", 5)] or "").strip(),
            "kind": str(row_vals[col_map.get("kind", 2)] or "").strip() if "kind" in col_map else "",
            "ipc": str(row_vals[col_map.get("ipc", 4)] or "").strip() if "ipc" in col_map else "",
        })

    if on_step:
        on_step(f"[Excel Reader] Parsed {len(rows)} patent entries")

    wb.close()
    return rows


def _map_columns(headers):
    """Map header names to column indices."""
    col_map = {}
    for i, h in enumerate(headers):
        h_upper = h.upper()
        if h_upper == "ID":
            col_map["id"] = i
        elif h_upper == "TITLE":
            col_map["title"] = i
        elif h_upper == "APPLICANT":
            col_map["applicant"] = i
        elif "APPL" in h_upper:
            # Must come AFTER "APPLICANT" check — "Appl.No" contains "APPL"
            col_map["appl_no"] = i
        elif h_upper == "IPC":
            col_map["ipc"] = i
        elif h_upper == "KIND":
            col_map["kind"] = i
    return col_map


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

    if mode == "wipo_download":
        step("[Mode: WIPO Download] Downloading Excel from PatentScope...")
        time.sleep(STEP_DELAY)

        def do_download():
            return download_wipo_excel(on_step=on_step)

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

    # --- Step 5: Choose mode — pipeline (large) or sequential (small) ---
    if len(patent_rows) >= PIPELINE_THRESHOLD:
        return _run_pipeline_mode(
            patent_rows, file_path, agent_name, strategy,
            start_time, step, browser_event,
        )

    # --- Sequential mode (< PIPELINE_THRESHOLD rows) ---
    step("Launching browser for WIPO scraping...")
    step("A Chromium window will open — solve any CAPTCHAs when prompted.")
    time.sleep(STEP_DELAY)

    results = []
    found_count = 0
    not_found_count = 0
    error_count = 0
    total = len(patent_rows)

    patent_browser = PatentBrowser(headless=False, on_step=on_step)
    try:
        patent_browser.start()
    except Exception as e:
        step(f"ERROR: Could not launch browser: {e}")
        return _failure(f"Browser launch failed: {e}")

    try:
        for idx, row_data in enumerate(patent_rows, start=1):
            patent_id = row_data["id"]
            title = row_data["title"]
            url = id_to_url(patent_id)
            country = extract_country(row_data["appl_no"])
            doc_id = patent_id.replace("/", "_")

            step(f"[Row {idx}/{total}] Processing: {patent_id}")

            # Dashboard browser preview: navigate
            browser_event({
                "event": "navigate",
                "url": url,
                "row": idx,
                "total": total,
                "patent_id": patent_id,
                "title": title,
                "applicant": row_data["applicant"],
                "country": country,
            })

            # Use Playwright browser to scrape patent & download RO/101 PDF
            step(f"[Row {idx}] [Browser] Opening patent page & searching for RO/101 PDF...")
            pdf_path = patent_browser.scrape_patent(url, doc_id, on_step=on_step)

            if not pdf_path:
                browser_event({
                    "event": "no_pdf",
                    "url": url,
                    "row": idx,
                    "total": total,
                    "patent_id": patent_id,
                })
                step(f"[Row {idx}] No RO/101 PDF found")
                results.append(_row_result(
                    idx, row_data, url, country, "not_found",
                    reason="No RO/101 PDF found on patent page",
                ))
                not_found_count += 1
                continue

            # PDF downloaded — extract contacts
            browser_event({
                "event": "extracting",
                "url": url,
                "row": idx,
                "total": total,
                "patent_id": patent_id,
            })
            step(f"[Row {idx}] [PDF Extractor] Extracting contacts...")
            contacts = extract_contacts_from_pdf(pdf_path, on_step=on_step)

            emails = contacts.get("emails", [])
            phones = contacts.get("phones", [])
            name = contacts.get("name", "")
            status = contacts["status"]

            # Dashboard browser preview: contacts result
            browser_event({
                "event": "contacts",
                "url": url,
                "row": idx,
                "total": total,
                "patent_id": patent_id,
                "title": title,
                "emails": emails,
                "phones": phones,
                "name": name,
                "status": status,
                "found_count": found_count + (1 if status == "found" else 0),
                "not_found_count": not_found_count + (1 if status == "not_found" else 0),
                "error_count": error_count,
            })

            if status == "found":
                found_count += 1
                step(
                    f"[Row {idx}] FOUND: "
                    f"{', '.join(emails[:2]) if emails else 'no email'} | "
                    f"{', '.join(phones[:2]) if phones else 'no phone'}"
                )
            elif status == "not_found":
                not_found_count += 1
                step(f"[Row {idx}] No contact info found in PDF")
            else:
                error_count += 1
                step(f"[Row {idx}] Error: {contacts.get('error', 'Unknown')}")

            results.append(_row_result(
                idx, row_data, url, country, status,
                emails=emails, phones=phones, name=name,
            ))

            time.sleep(0.5)

    finally:
        step("[Browser] Closing browser...")
        patent_browser.close()

    # --- Step 6: Generate Work Report Excel ---
    step("Generating Work Report Excel...")
    time.sleep(STEP_DELAY)

    output_path = generate_work_report(results, on_step=step)
    step(f"Output saved: {Path(output_path).name}")
    time.sleep(STEP_DELAY)

    # --- Step 7: Self-test ---
    step("Running self-tests...")
    time.sleep(STEP_DELAY)

    agent_result = {
        "status": "success",
        "results": results,
        "summary": {
            "total": total,
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

    if test_result["passed"]:
        step(f"All {test_result['total']} self-tests passed!")
    else:
        step(f"Self-tests: {test_result['passed_count']}/{test_result['total']} passed")

    # --- Step 8: Save learning ---
    execution_time = time.time() - start_time
    insight = (
        f"Processed {total} rows: {found_count} contacts found, "
        f"{not_found_count} not found, {error_count} errors"
    )
    save_learning(
        agent_name, "process_excel",
        "success" if found_count > 0 or not_found_count > 0 else "partial",
        insight, strategy, execution_time,
    )

    step(f"Learning saved. Total time: {execution_time:.1f}s")
    time.sleep(STEP_DELAY)

    step(
        f"DONE — {found_count} contacts found, {not_found_count} not found, "
        f"{error_count} errors out of {total} rows"
    )

    agent_result["execution_time"] = round(execution_time, 2)
    agent_result["attempts"] = 1
    return agent_result


# ---------------------------------------------------------------------------
# Pipeline mode — parallel processing for large datasets
# ---------------------------------------------------------------------------
def _run_pipeline_mode(patent_rows, file_path, agent_name, strategy,
                       start_time, step, browser_event):
    """Run the parallel pipeline for 50+ rows.  No artificial delays."""
    step(f"[Pipeline] Large dataset ({len(patent_rows)} rows) — parallel pipeline mode")
    step(f"[Pipeline] {DEFAULT_BROWSER_WORKERS} browsers + {DEFAULT_DOWNLOAD_WORKERS} downloaders + {DEFAULT_OCR_WORKERS} OCR")

    # Check for resume
    resume_path = ProgressFile.find_latest(file_path)
    if resume_path:
        completed = ProgressFile.load_completed(resume_path)
        step(f"[Pipeline] Resuming — {len(completed)}/{len(patent_rows)} already done")
    else:
        resume_path = None

    # Build and run pipeline
    pipeline = PipelinePCT(
        patent_rows=patent_rows,
        on_step=step,
        browser_workers=DEFAULT_BROWSER_WORKERS,
        download_workers=DEFAULT_DOWNLOAD_WORKERS,
        ocr_workers=DEFAULT_OCR_WORKERS,
        headless=True,
        resume_path=resume_path,
        input_file=file_path,
    )

    results = pipeline.run()

    # Generate Work Report (no delay)
    step("Generating Work Report Excel...")
    output_path = generate_work_report(results, on_step=step)
    step(f"Output saved: {Path(output_path).name}")

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
    return agent_result


# ---------------------------------------------------------------------------
# Output generator — Work Report format
# ---------------------------------------------------------------------------
WORK_REPORT_HEADERS = [
    "Publication Number", "Title", "Application No", "Applicant",
    "Url", "Cat", "Phone No", "Email", "Name", "Country",
    "Date", "Researcher", "Deadline",
]


def generate_work_report(results, on_step=None):
    """Generate a Work Report Excel matching the standard output format."""
    wb = openpyxl.Workbook()
    ws = wb.active

    # Sheet name: "Work Report DD-Month-YYYY"
    date_str = datetime.now().strftime("%d-%B-%Y")
    sheet_name = f"Work Report {date_str}"
    ws.title = sheet_name[:31]

    # Write headers with bold font
    for col, header in enumerate(WORK_REPORT_HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)

    run_date = f"Shared - {datetime.now().strftime('%d-%m-%Y')}"

    for i, r in enumerate(results, start=2):
        ws.cell(row=i, column=1, value=r.get("patent_id", ""))
        ws.cell(row=i, column=2, value=r.get("title", ""))
        ws.cell(row=i, column=3, value=r.get("appl_no", ""))
        ws.cell(row=i, column=4, value=r.get("applicant", ""))
        ws.cell(row=i, column=5, value=r.get("url", ""))
        ws.cell(row=i, column=6, value="")             # Cat — filled manually
        ws.cell(row=i, column=7, value="; ".join(r.get("phones", [])))
        ws.cell(row=i, column=8, value="; ".join(r.get("emails", [])))
        ws.cell(row=i, column=9, value=r.get("name", ""))
        ws.cell(row=i, column=10, value=r.get("country", ""))
        ws.cell(row=i, column=11, value=run_date)
        ws.cell(row=i, column=12, value="")            # Researcher — filled manually
        ws.cell(row=i, column=13, value="")            # Deadline — filled manually

    # Save to outputs/
    output_dir = Path(__file__).parent.parent.parent / "outputs"
    output_dir.mkdir(exist_ok=True)

    output_name = f"Work Report {date_str}.xlsx"
    output_path = output_dir / output_name
    counter = 2
    while output_path.exists():
        output_name = f"Work Report {date_str} book{counter}.xlsx"
        output_path = output_dir / output_name
        counter += 1

    wb.save(str(output_path))

    if on_step:
        on_step(f"[Output] Work Report saved: {output_name} ({len(results)} rows)")

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
        "country": country,
        "status": status,
        "emails": emails or [],
        "phones": phones or [],
        "name": name,
        "reason": reason,
    }


def _failure(error_msg):
    """Build a standardised failure result."""
    return {
        "status": "failure",
        "error": error_msg,
        "results": [],
        "summary": {"total": 0, "found": 0, "not_found": 0, "errors": 0},
    }
