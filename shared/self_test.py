class SelfTest:
    """Validation framework for agent output. Each agent defines its own tests."""

    def __init__(self, agent_name, validations):
        self.agent_name = agent_name
        self.validations = validations

    def run(self, result):
        """Run all validations against the result. Returns pass/fail report."""
        failures = []
        passed_tests = []

        for v in self.validations:
            try:
                if v["check"](result):
                    passed_tests.append(v["name"])
                else:
                    failures.append({"name": v["name"], "message": v["message"]})
            except Exception as e:
                failures.append({"name": v["name"], "message": f"Test error: {e}"})

        return {
            "passed": len(failures) == 0,
            "total": len(self.validations),
            "passed_count": len(passed_tests),
            "failed_count": len(failures),
            "passed_tests": passed_tests,
            "failures": failures,
        }
