import ast
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from shared.agent_registry import discover_agents, get_agent_runner
from .agent import AGENT_CONFIG, get_dashboard_data, run_agent
from .tasks import TASKS
from .tools import TOOLS
from .tests import tests


class PlaceholderTests(unittest.TestCase):
    def test_registered_but_inactive(self):
        configs = discover_agents()
        agent = next(a for a in configs if a["module_name"] == "lexmom_marketing_agent")
        self.assertEqual(agent["name"], "Lexmom Marketing Agent")
        self.assertEqual(agent["status"], "pending_setup")
        self.assertFalse(agent["execution_enabled"])
        self.assertEqual(agent["sub_agents"], [])

    def test_direct_runner_only_returns_setup_status(self):
        with patch("os.environ", {}):
            result = get_agent_runner("lexmom_marketing_agent")(
                input_data={"publish": True}, on_step=lambda _: self.fail("Unexpected work")
            )
        self.assertEqual(result["status"], "pending_setup")
        self.assertFalse(result["executionEnabled"])
        self.assertTrue(result["tests"]["passed"])
        self.assertEqual(TASKS, ())
        self.assertEqual(TOOLS, ())

    def test_self_tests_reject_activation(self):
        self.assertTrue(tests.run(get_dashboard_data())["passed"])
        self.assertFalse(tests.run({**get_dashboard_data(), "executionEnabled": True})["passed"])

    def test_config_has_no_credentials_or_llm_dependency(self):
        self.assertFalse(AGENT_CONFIG["requires_llm"])
        self.assertEqual(run_agent()["schedule"], "Not configured")

    def test_server_rejects_execution_before_starting_work(self):
        # Exercise the real launch guard without importing server startup jobs.
        from starlette.responses import JSONResponse

        project = Path(__file__).resolve().parents[2]
        tree = ast.parse((project / "server.py").read_text(encoding="utf-8"))
        launch = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "_launch_agent_run")
        namespace = {
            "discover_agents": lambda: [{**AGENT_CONFIG, "module_name": "lexmom_marketing_agent"}],
            "JSONResponse": JSONResponse,
        }
        exec(compile(ast.Module(body=[launch], type_ignores=[]), "server.py", "exec"), namespace)
        result = namespace["_launch_agent_run"]("lexmom_marketing_agent", {"publish": True})
        self.assertFalse(result["ok"])
        self.assertEqual(result["response"].status_code, 409)
        self.assertEqual(json.loads(result["response"].body)["status"], "pending_setup")

    @unittest.skipUnless(shutil.which("node"), "Node is required for the frontend check")
    def test_frontend_shows_setup_without_run_controls(self):
        project = Path(__file__).resolve().parents[2]
        script = """
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const main = {innerHTML: ''};
const context = {
    localStorage: {getItem: () => null},
    document: {
        addEventListener: () => {}, getElementById: () => main,
        createElement: () => ({textContent: '', get innerHTML() {return this.textContent;}}),
    },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), context);
vm.runInContext(`state.selectedAgent = {
    name: 'Lexmom Marketing Agent', ui_type: 'pending_setup',
    description: 'Reserved for Lexmom marketing.', role: 'Marketing',
    setup_message: 'Awaiting instructions.'
}; renderMain();`, context);
assert(main.innerHTML.includes('Lexmom Marketing Agent'));
assert(main.innerHTML.includes('Awaiting instructions'));
assert(!main.innerHTML.includes('run-btn'));
assert(!main.innerHTML.includes('Run Agent'));
"""
        result = subprocess.run(["node"], input=script, text=True, capture_output=True,
                                cwd=project, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
