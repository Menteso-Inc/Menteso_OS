"""Regression checks for the activated research-only manager connector."""

import ast
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from starlette.responses import JSONResponse

from shared.research_runtime import ResearchSession
from .agent import AGENT_CONFIG, AGENT_NAME, CAPABILITIES, get_dashboard_data, resolve_research_artifact, run_agent
from .tools import validate_profile

PROJECT = Path(__file__).resolve().parents[2]


def server_function(name, namespace):
    """Exercise actual route/launch code without importing server startup jobs."""
    tree = ast.parse((PROJECT / "server.py").read_text(encoding="utf-8"))
    node = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == name)
    node.decorator_list = []
    namespace = {"JSONResponse": JSONResponse, "Request": object,
                 "Body": lambda **kwargs: None, **namespace}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "server.py", "exec"), namespace)
    return namespace[name]


def child_result(status="success", **overrides):
    firm = {"domain": "evidenced.example", "name": "Evidenced Firm", "country": "India",
            "fit_status": "qualified", "outreach_eligible": False}
    return {"status": status, "run_id": "child-test", "data": {"firms": [firm],
            "summary": {"qualified": 1, "needs_research": 0, "excluded": 0}}, "rows": [firm],
            "artifacts": [], "tests": {"passed": True}, **overrides}


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.session = ResearchSession(AGENT_NAME, "manager-test", state_dir=self.root,
                                       memory_dir=self.root / "memory")

    def tearDown(self):
        self.temporary.cleanup()

    def execute(self, child, profile=None, **kwargs):
        with patch("agents.lexmom_marketing_agent.agent.delegate_research", return_value=child) as delegate:
            result = run_agent(profile or {"countries": ["India", "United States"]},
                               session=self.session, **kwargs)
        return result, delegate

    def test_manager_enabled_with_only_approved_child(self):
        self.assertEqual(AGENT_CONFIG["name"], "Lexmom Sub Manager")
        self.assertTrue(AGENT_CONFIG["execution_enabled"])
        self.assertEqual(AGENT_CONFIG["sub_agents"], ["Prospect Research", "Email Campaign", "Social Media Posting"])
        self.assertEqual(CAPABILITIES, {"research": True, "outreach": False, "ads": False,
                                       "sales_conversation": False, "customer_success": False})

    def test_real_delegation_preserves_profile_records_and_status(self):
        child = child_result()
        result, delegate = self.execute(child)
        request = delegate.call_args.args[0]
        self.assertEqual(request["countries"], ["India", "United States"])
        self.assertEqual(request["mode"], "live")
        self.assertEqual(result["run_id"], child["run_id"])
        self.assertEqual(result["data"], child["data"])
        self.assertTrue(result["tests"]["passed"])
        self.assertEqual(self.session.load_memory()["stats"]["evaluated_runs"], 1)
        self.assertNotIn("evidenced.example", self.session.memory_path.read_text())
        stored = json.loads(self.session.artifact_path.read_text())
        self.assertEqual(stored["data"]["firms"], [])

    def test_failure_partial_cancelled_remain_distinct(self):
        for status in ("failure", "partial", "cancelled"):
            with self.subTest(status=status):
                self.session = ResearchSession(AGENT_NAME, status, state_dir=self.root,
                                               memory_dir=self.root / "memory")
                result, _ = self.execute(child_result(status, errors=["Provider unavailable"]))
                self.assertEqual(result["status"], status)
                self.assertEqual(result["errors"], ["Provider unavailable"])
        memory = self.session.load_memory()
        self.assertEqual(memory["stats"]["total_runs"], 3)
        self.assertEqual(memory["stats"]["evaluated_runs"], 1)

    def test_preflight_failure_not_an_evaluated_failure(self):
        result, _ = self.execute(child_result("failure", preflight=True))
        self.assertEqual(result["status"], "failure")
        self.assertEqual(self.session.load_memory()["stats"]["evaluated_runs"], 0)

    def test_manager_changes_internal_strategy_after_evaluated_failure(self):
        self.execute(child_result("failure"))
        self.session = ResearchSession(AGENT_NAME, "manager-second", state_dir=self.root,
                                       memory_dir=self.root / "memory")
        _, delegate = self.execute(child_result())
        self.assertEqual(delegate.call_args.kwargs["initial_strategy"], "focused")
        self.assertEqual(delegate.call_args.args[0]["target_count"], 25)

    def test_child_exception_is_logged_as_evaluated_failure(self):
        with patch("agents.lexmom_marketing_agent.agent.delegate_research", side_effect=RuntimeError("Child crashed")):
            result = run_agent(session=self.session)
        self.assertEqual(result["status"], "failure")
        self.assertIn("Child crashed", result["errors"])
        self.assertEqual(self.session.load_memory()["stats"]["failed_runs"], 1)

    def test_cancellation_callback_forwarded_and_controls_not_in_profile(self):
        cancelled = lambda: True
        result, delegate = self.execute(child_result("cancelled"), profile={
            "stop_requested": cancelled, "run_id": "server-run", "register_stop_handler": Mock(),
            "get_live_fast_level": Mock()})
        self.assertIs(delegate.call_args.kwargs["cancelled"], cancelled)
        self.assertNotIn("stop_requested", delegate.call_args.args[0])
        self.assertEqual(result["status"], "cancelled")

    def test_invalid_profile_never_calls_child(self):
        result, delegate = self.execute(child_result(), profile={"send_email": True})
        delegate.assert_not_called()
        self.assertEqual(result["status"], "failure")
        self.assertEqual(self.session.load_memory()["stats"]["evaluated_runs"], 0)

    def test_unverified_or_outreach_eligible_handoff_rejected(self):
        for child in (child_result(tests={"passed": False}), child_result(data={
                "firms": [{"outreach_eligible": True}], "summary": {}})):
            result, _ = self.execute(child)
            self.assertEqual(result["status"], "failure")
            self.assertFalse(result["tests"]["passed"])

    def test_browser_rejects_fixtures_pricing_and_unapproved_actions(self):
        for payload in ({"mode": "fixture"}, {"unit_costs": {"llm_calls": 0}},
                        {"fixture_pages": []}, {"publish": True}, {"artifact_path": "C:/secret"},
                        {"size_min": 51, "size_max": 50}, {"target_count": 26}):
            with self.subTest(payload=payload), self.assertRaises((ValueError, TypeError)):
                validate_profile(payload, browser=True)

    def test_server_invalid_input_rejected_before_thread_spawn(self):
        launch = server_function("_launch_agent_run", {
            "discover_agents": lambda: [{**AGENT_CONFIG, "module_name": AGENT_NAME}]})
        for payload in ({"publish": True}, {"mode": "fixture"}, {"seed_urls": ["file:///secret"]}):
            response = launch(AGENT_NAME, payload)
            self.assertFalse(response["ok"])
            self.assertEqual(response["response"].status_code, 422)

    def test_specialist_http_cannot_bypass_live_manager_guards(self):
        launch = server_function("_launch_agent_run", {"discover_agents": lambda: [{
            "module_name": "prospect_research_agent", "hidden_from_dashboard": True}]})
        result = launch("prospect_research_agent", {"mode": "fixture"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["response"].status_code, 409)

    def test_server_accepts_valid_profile_and_supplies_stop_control(self):
        thread = Mock()
        threads = Mock(return_value=thread)
        controls = {}
        launch = server_function("_launch_agent_run", {
            "discover_agents": lambda: [{**AGENT_CONFIG, "module_name": AGENT_NAME}],
            "time": SimpleNamespace(time=lambda: 1), "secrets": SimpleNamespace(token_hex=lambda _: "abcd"),
            "_get_run_status": lambda name: {"status": "idle"},
            "threading": SimpleNamespace(Event=lambda: SimpleNamespace(is_set=lambda: False), Thread=threads),
            "RUN_CONTROLS": controls, "RUN_LIVE_STATUS": {}, "_now_iso": lambda: "now"})
        result = launch(AGENT_NAME, {"countries": ["India"]})
        self.assertTrue(result["ok"])
        thread.start.assert_called_once()
        self.assertIn(AGENT_NAME, controls)

    def test_http_get_cannot_launch_and_viewer_cannot_post(self):
        get = server_function("run_agent_sse", {})
        self.assertEqual(asyncio.run(get(AGENT_NAME)).status_code, 405)
        start = Mock(return_value="accepted")
        post = server_function("run_agent_sse_post", {"_start_agent_run": start})
        viewer = SimpleNamespace(state=SimpleNamespace(user={"role": "viewer"}))
        operator = SimpleNamespace(state=SimpleNamespace(user={"role": "operator"}))
        self.assertEqual(asyncio.run(post(AGENT_NAME, viewer, {})).status_code, 403)
        start.assert_not_called()
        self.assertEqual(asyncio.run(post(AGENT_NAME, operator, {})), "accepted")

    def test_http_viewer_cannot_stop_or_clear_manager(self):
        viewer = SimpleNamespace(state=SimpleNamespace(user={"role": "viewer"}))
        for name in ("stop_agent_run", "force_clear_agent_run"):
            handler = server_function(name, {})
            self.assertEqual(asyncio.run(handler(AGENT_NAME, viewer)).status_code, 403)

    def test_downloads_require_manifest_and_stay_inside_run(self):
        child = ResearchSession("prospect_research_agent", "child-test", state_dir=self.root,
                                memory_dir=self.root / "memory")
        child.run_dir.mkdir(parents=True, exist_ok=True)
        dataset = child.run_dir / "firms.csv"
        dataset.write_text("name,country\nEvidenced Firm,India\n")
        private = child.run_dir / "private.txt"
        private.write_text("not exported")
        self.assertIsNone(resolve_research_artifact(child.run_id, "firms.csv", state_root=self.root))
        child.finish(child_result(artifacts=[{"path": str(dataset)}]), "success", "standard", "", 0)
        self.assertEqual(resolve_research_artifact(child.run_id, "firms.csv", state_root=self.root), dataset)
        self.assertEqual(resolve_research_artifact(child.run_id, "result.json", state_root=self.root), child.artifact_path)
        for run, filename in (("../", "firms.csv"), (child.run_id, "../private.txt"),
                              (child.run_id, "private.txt"), (child.run_id, "completion.json")):
            self.assertIsNone(resolve_research_artifact(run, filename, state_root=self.root))

    def test_dashboard_reloads_authoritative_dataset_after_restart(self):
        child = ResearchSession("prospect_research_agent", "child-test", state_dir=self.root,
                                memory_dir=self.root / "memory")
        child.finish(child_result(), "success", "standard", "", 0)
        self.execute(child_result(artifacts=[{"path": str(child.artifact_path)}]))
        resolver = lambda run, name: resolve_research_artifact(run, name, state_root=self.root)
        with patch("agents.lexmom_marketing_agent.agent.STATE_FILE", self.session.agent_dir / "last-research.json"), \
             patch("agents.lexmom_marketing_agent.agent.resolve_research_artifact", side_effect=resolver), \
             patch("agents.lexmom_marketing_agent.agent.load_memory", return_value=self.session.load_memory()):
            snapshot = get_dashboard_data()
        self.assertEqual(snapshot["lastResult"]["data"]["firms"][0]["name"], "Evidenced Firm")
        self.assertFalse(snapshot["capabilities"]["outreach"])
        self.assertEqual(len(snapshot["directorySources"]), 16)
        self.assertEqual(snapshot["directorySources"][0]["name"], "Justia")
        self.assertEqual(snapshot["directorySources"][0]["state"], "restricted")

    @unittest.skipUnless(shutil.which("node"), "Node is required for the frontend check")
    def test_saved_profile_dashboard_evidence_and_safe_exports_render(self):
        script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const main = {innerHTML: ''}, nodes = {};
const node = id => nodes[id] ||= {focus() {}, click() { this.onclick?.(); }};
const context = {URL, setTimeout:()=>1, clearTimeout:()=>{}, location:{hash:''}, history:{replaceState() {}}, localStorage: {getItem: () => null}, document: {
    querySelectorAll: () => [],
    addEventListener: () => {}, getElementById: id => id === 'main-content' ? main : main.innerHTML.includes('id="'+id+'"') ? node(id) : null,
    createElement: () => ({textContent: '', get innerHTML() {return this.textContent.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');}})
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), context);
vm.runInContext(`state.selectedAgent = {name: 'Lexmom Sub Manager', module_name:'lexmom_marketing_agent',ui_type:'lexmom_research'};
state.lastResult={status:'partial',run_id:'research-1',data:{candidates:[{url:'javascript:alert(1)',title:'<script>bad</script>',query:'law firms',status:'already_known',reason:'Recent saved research'}],summary:{qualified:1},firms:[{
name:'Sample Firm',domain:'sample.example',website:'https://sample.example',country:'India',fit_status:'needs_research',size:null,
fit_reasons:['Size unresolved'],contacts:[],evidence:[{field:'country',value:'India',source_url:'https://sample.example/about',excerpt:'India office'}]
}]},artifacts:[{path:'/runtime/research-1/firms.csv'}]}; renderMain();`, context);
assert(main.innerHTML.includes('Lexmom Sub Manager'));
assert(main.innerHTML.includes('Run all agents'));
assert(main.innerHTML.includes('Total spend'));
assert(main.innerHTML.includes('Total revenue'));
assert(main.innerHTML.includes('Payment attribution not connected'));
assert(!main.innerHTML.includes('Sample Firm'));
assert.strictEqual(typeof node('lexmom-run').onclick, 'function');
node('lexmom-tab-1').click();
assert(!main.innerHTML.includes('id="lexmom-run"'));
assert(main.innerHTML.includes('aria-selected="true" tabindex="0">Prospect Research'));
assert(main.innerHTML.includes('id="lexmom-source-form"'));
assert(main.innerHTML.includes('id="lexmom-source-url"'));
assert(!main.innerHTML.includes('name="countries"'));
assert(!main.innerHTML.includes('name="target_segments"'));

assert(main.innerHTML.includes('Last run: partial'));
assert(!main.innerHTML.includes('India office'));
assert(main.innerHTML.includes('Discovery decisions (1)'));
assert(main.innerHTML.includes('already known'));
assert(!main.innerHTML.includes('<script>bad</script>'));
assert(!main.innerHTML.includes('href="javascript:'));
assert(main.innerHTML.includes('/artifacts/research-1/firms.csv'));
assert(!main.innerHTML.includes('Scrollable firm records'));
vm.runInContext(`state.lexmom.snapshot ||= {}; state.lexmom.snapshot.prospectInventory=[{
name:'Saved Firm',domain:'saved.example',website:'https://saved.example',fit_status:'qualified',
product_assessments:{manage:{status:'potential_fit',confidence:'low',reasons:['<script>bad</script>'],interest_status:'unknown'},launch:{status:'unknown',reasons:[]}},
primary_product:'manage',contacts:[{email:'info@saved.example',inbox_type:'generic',research_ready:false,readiness_reasons:['Email verification is stale']}],
fit_reasons:[],evidence:[],personalization_briefs:[]}];
state.lexmom.snapshot.leadTable={total:1,hot:0,warm:0,rules:{new:'No recorded activity'},rows:[{email:'info@saved.example',firm:'Saved Firm',website:'https://saved.example',product:'manage',temperature:'new',activity:{opens:0,clicks:0,replies:0},hold_reasons:['Email verification is stale']}]}; renderMain();`, context);
assert(main.innerHTML.includes('Qualified &amp; verified') || main.innerHTML.includes('Qualified & verified'));
assert(main.innerHTML.includes('Needs research'));
assert(main.innerHTML.includes('lexmom-lead-readiness'));
assert(main.innerHTML.includes('Saved Firm'));
assert(main.innerHTML.includes('data-lexmom-lead-details="0"'));
assert(main.innerHTML.includes('aria-haspopup="dialog"'));
assert(!main.innerHTML.includes('Email verification is stale'));
const drawer = vm.runInContext('renderLexmomLeadDrawer(state.lexmom.snapshot.leadTable.rows[0],state.lexmom.snapshot.leadTable)',context);
assert(drawer.includes('Email verification is stale'));
assert(drawer.includes('Close lead details'));
const directorySources = vm.runInContext(`renderLexmomDirectorySources({directorySources:[{name:'Justia',homepage:'https://lawyers.justia.com/',state:'restricted',reason:'<script>bad</script>',terms_url:'javascript:alert(1)',reviewed_on:'2026-10-20'}]})`, context);
assert(directorySources.includes('Directory sources (1)'));
assert(directorySources.includes('restricted'));
assert(directorySources.includes('2026-10-20'));
assert(!directorySources.includes('<script>bad</script>'));
assert(!directorySources.includes('href="javascript:'));
const sourcePreview = vm.runInContext(`state.lexmom.sourceImport={status:'partial',source_url:'javascript:alert(1)',pages_read:1,message:'<script>bad</script>',records:[{name:'<img onerror=bad>',email:'safe@example.org',evidence_excerpt:'<svg onload=bad>',change:'new'}]}; renderLexmomSourceImport()`,context);
assert(sourcePreview.includes('Continue batch'));
assert(sourcePreview.includes('Unverified observations'));
assert(sourcePreview.includes('data-lexmom-source-details="0"'));
assert(!sourcePreview.includes('<script>bad</script>'));
assert(!sourcePreview.includes('<img onerror='));
assert(!sourcePreview.includes('href="javascript:'));
const unsafeDrawer = vm.runInContext(`renderLexmomLeadDrawer({email:'safe@example.org',name:'<script>bad</script>',website:'javascript:alert(1)',hold_reasons:['<script>bad</script>'],product_assessments:{manage:{reasons:['<img onerror=bad>']}},evidence:[{excerpt:'<svg onload=bad>',source_url:'javascript:alert(1)'}]}, {rules:{}})`,context);
assert(!unsafeDrawer.includes('<script>bad</script>'));
assert(!unsafeDrawer.includes('<img onerror='));
assert(!unsafeDrawer.includes('<svg onload='));
assert(!unsafeDrawer.includes('href="javascript:'));
assert.strictEqual((main.innerHTML.match(/class="lexmom-table lexmom-lead-table"/g)||[]).length,1);
assert(!main.innerHTML.includes('Unique firms'));
assert(!main.innerHTML.includes('<script>bad</script>'));
assert(!main.innerHTML.includes('>Send email<'));
assert.strictEqual(vm.runInContext("lexmomSourceLink('javascript:alert(1)')", context), '');
node('lexmom-tab-1').onkeydown({key:'ArrowLeft',preventDefault() {}});
assert(main.innerHTML.includes('Total spend'));
vm.runInContext(`state.lexmom.snapshot={businessSummary:{qualified_leads:1,history_complete:true,reserved_cost_usd:.3},profileError:'Invalid profile'}; renderMain();`,context);
assert(main.innerHTML.includes('id="lexmom-run" disabled'));
(async () => {
    await node('lexmom-run').onclick(); // blocked profile never calls the executor
    vm.runInContext(`state.lexmom.snapshot.profileError=''; let dispatches=0;
        loadAgentRunStatus=async () => 'idle';
        runAgent=async (name, options) => { if(name!=='lexmom_marketing_agent' || options.method!=='POST' || Object.keys(options.body).length) throw Error('Wrong workflow'); dispatches++; };
        renderMain();`,context);
    await Promise.all([node('lexmom-run').onclick(),node('lexmom-run').onclick()]);
    assert.strictEqual(vm.runInContext('dispatches',context),1);
})().catch(error => { console.error(error); process.exitCode=1; });
"""
        result = subprocess.run(["node"], input=script, text=True, capture_output=True,
                                cwd=PROJECT, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
