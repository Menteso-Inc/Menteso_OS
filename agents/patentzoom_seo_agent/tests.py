from shared.self_test import SelfTest

tests = SelfTest(
    agent_name="patentzoom_seo_agent",
    validations=[
        {
            "name": "output_is_dict",
            "check": lambda r: isinstance(r, dict),
            "message": "Agent returned a non-dict result",
        },
        {
            "name": "has_status",
            "check": lambda r: isinstance(r.get("status"), str) and len(r.get("status", "")) > 0,
            "message": "Missing status field",
        },
        {
            "name": "has_output_logs",
            "check": lambda r: isinstance(r.get("outputLogs", []), list),
            "message": "Missing output logs list",
        },
        {
            "name": "success_has_keyword",
            "check": lambda r: r.get("status") != "success" or bool(r.get("primaryKeyword")),
            "message": "Successful run missing primary keyword",
        },
        {
            "name": "success_has_post_status",
            "check": lambda r: r.get("status") != "success" or bool(r.get("postStatus")),
            "message": "Successful run missing post status",
        },
    ],
)

