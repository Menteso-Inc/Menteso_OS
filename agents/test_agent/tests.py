from shared.self_test import SelfTest

tests = SelfTest(
    agent_name="test_agent",
    validations=[
        {
            "name": "output_not_empty",
            "check": lambda r: r is not None and isinstance(r, dict),
            "message": "Agent returned empty or non-dict output",
        },
        {
            "name": "has_system_info",
            "check": lambda r: "system" in r and "os" in r.get("system", {}),
            "message": "Missing system information",
        },
        {
            "name": "has_python_info",
            "check": lambda r: "python" in r and "version" in r.get("python", {}),
            "message": "Missing Python information",
        },
        {
            "name": "has_disk_info",
            "check": lambda r: "disk" in r and "total_gb" in r.get("disk", {}),
            "message": "Missing disk information",
        },
        {
            "name": "has_timestamp",
            "check": lambda r: "timestamp" in r and len(r.get("timestamp", "")) > 0,
            "message": "Missing timestamp",
        },
        {
            "name": "has_env_status",
            "check": lambda r: "env_status" in r and isinstance(r.get("env_status"), dict),
            "message": "Missing environment status check",
        },
    ],
)
