TASKS = {
    "process_excel": {
        "description": (
            "Process a patent Excel sheet: for each row with a WIPO URL, "
            "visit the patent detail page, find the RO/101 or 306 PDF, "
            "download it, extract email/phone contacts, and produce an "
            "output Excel matching the user's original format."
        ),
        "expected_output": "Excel file with contact columns (email, phone) populated",
    },
    "download_wipo": {
        "description": (
            "Download the weekly browse Excel from WIPO PatentScope, "
            "apply optional filters, and return the file path."
        ),
        "expected_output": "Path to downloaded Excel file",
    },
}
