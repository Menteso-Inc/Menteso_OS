from shared.self_test import SelfTest

tests = SelfTest(
    agent_name="pct_agent",
    validations=[
        {
            "name": "output_not_empty",
            "check": lambda r: r is not None and isinstance(r, dict),
            "message": "Agent returned empty or non-dict output",
        },
        {
            "name": "has_status",
            "check": lambda r: "status" in r,
            "message": "Missing status field in output",
        },
        {
            "name": "has_results",
            "check": lambda r: "results" in r or "error" in r,
            "message": "Missing results or error field",
        },
        {
            "name": "has_summary",
            "check": lambda r: "summary" in r,
            "message": "Missing summary field",
        },
        {
            "name": "results_is_list",
            "check": lambda r: isinstance(r.get("results", []), list),
            "message": "Results field is not a list",
        },
        {
            "name": "rows_are_unique",
            "check": lambda r: len([item.get("row") for item in r.get("results", [])])
            == len(set(item.get("row") for item in r.get("results", []))),
            "message": "Duplicate output rows detected after pipeline merge",
        },
        {
            "name": "rows_are_sorted",
            "check": lambda r: [item.get("row") for item in r.get("results", [])]
            == sorted(item.get("row") for item in r.get("results", [])),
            "message": "Output rows are not sorted back into original Excel order",
        },
        {
            "name": "summary_matches_results",
            "check": lambda r: r.get("summary", {}).get("processed", len(r.get("results", [])))
            == len(r.get("results", [])),
            "message": "Summary processed count does not match merged result count",
        },
    ],
)
