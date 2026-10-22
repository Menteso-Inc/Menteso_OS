"""Isolated authenticated dashboard adapter; unrelated agents stay on their server.

Only the gateway's exact dashboard/list routes and Lexmom prefix point here.
Authentication is checked with the existing server on every private request.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse

from agents.lexmom_marketing_agent.agent import AGENT_CONFIG, get_dashboard_data, resolve_research_artifact
from agents.lexmom_marketing_agent.tools import validate_profile, load_saved_profile
from agents.prospect_research_agent.agent import live_preflight, validate_request
from shared.memory import load_memory
from shared.research_runtime import _atomic_json

ROOT = Path(os.getenv("LEXMOM_RUNTIME_ROOT", "/home/menteso_os/agents/lexmom_sub_manager"))
STATIC = Path(__file__).resolve().parents[1] / "static"
UPSTREAM = "http://127.0.0.1:8010"
ORIGIN = "https://os.menteso.com"
NAME = "lexmom_marketing_agent"
BASE = "/api/agents/" + NAME
UNIT = "lexmom-research.service"
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
run_lock = asyncio.Lock()


async def upstream(request, path):
    async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
        return await client.get(UPSTREAM + path, headers={"Cookie": request.headers.get("cookie", "")})


async def authorize(request, *, write=False):
    try:
        response = await upstream(request, "/api/auth/me")
    except httpx.HTTPError:
        raise HTTPException(503, "Login service unavailable") from None
    if response.status_code != 200:
        raise HTTPException(401, "Login required")
    user = response.json().get("user", {})
    if write:
        if user.get("role") not in {"admin", "operator"}:
            raise HTTPException(403, "An operator account is required")
        if request.headers.get("origin") != ORIGIN:
            raise HTTPException(403, "A same-origin dashboard request is required")
    return user


def service_state():
    result = subprocess.run(["/usr/bin/systemctl", "show", UNIT, "-p", "ActiveState", "-p", "Result"],
                            capture_output=True, text=True, timeout=5, check=True)
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def control(action):
    if action not in {"start", "stop"}:
        raise ValueError("Unsupported service action")
    subprocess.run(["/usr/bin/sudo", "-n", "/usr/bin/systemctl", action, "--no-block", UNIT],
                   capture_output=True, timeout=10, check=True)


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def run_status():
    system = service_state()
    active = system.get("ActiveState")
    status = "stopping" if active == "deactivating" else "running" if active in {"active", "activating", "reloading"} else "idle"
    return {"status": status, "input": read_json(ROOT / "pilot.json", {}),
            "serviceResult": system.get("Result"), "receipt": read_json(ROOT / "state/status.json", {})}


def public_config():
    return {**AGENT_CONFIG, "module_name": NAME, "status": "pilot", "version": "0.3.0",
            "description": "Lexmom Sub Manager coordinates Prospect Research and paused Email Campaign preparation."}


IMPORTED_WORKLOADS = {
    "n8n_automation": ("n8n Automation", "Workflow platform"),
    "wlf_sdr": ("WLF SDR", "Sales workflows"),
}


def imported_workloads():
    """Expose a small migration receipt, never environment files or credentials."""
    receipt = read_json(ROOT / "state/imported-workloads.json", {})
    if receipt.get("verified") is not True:
        return []
    return [{"module_name": key, "name": title, "role": role,
             "ui_type": "paused_workload", "status": "paused", "hosted_on": "aws",
             "execution_enabled": False, "requires_llm": False,
             "description": "Preserved on Menteso OS. Execution is paused to prevent API spending.",
             "workflow_count": receipt.get("wlf_workflows" if key == "wlf_sdr" else "workflows", 0),
             "credential_count": receipt.get("wlf_credentials" if key == "wlf_sdr" else "credentials", 0),
             "verified_at": receipt.get("verified_at", ""),
             "sub_agents": []}
            for key, (title, role) in IMPORTED_WORKLOADS.items()]


def dashboard():
    data = get_dashboard_data()
    receipt = read_json(ROOT / "state/status.json", {})
    # Do not display the previous completed run as the current active run.
    data.update({"status": "pilot", "readinessLabel": "Live pilot",
                 "providerStatus": read_json(ROOT / "state/providers.json", {}),
                 "runState": run_status(), "deployment": "AWS",
                 "readinessMessage": "Research is deployed. Qualification and provider checks are shown below; outreach is not enabled."})
    if receipt.get("status") == "running":
        data["readinessLabel"] = "Research running"
    data['workflowAgents']=[{'id':'prospect_research_agent','name':'Prospect Research','enabled':True},
                           {'id':'email_campaign_agent','name':'Email Campaign','enabled':False},
                           {'id':'social_media_posting_agent','name':'Social Media Posting','enabled':False}]
    return data


@app.exception_handler(HTTPException)
async def exception_response(request, error):
    return JSONResponse({"error": error.detail}, status_code=error.status_code)


@app.get("/healthz")
async def health():
    return {"ok": True}


@app.get("/")
async def index(request: Request):
    try:
        await authorize(request)
    except HTTPException as error:
        if error.status_code == 401:
            return RedirectResponse("/login", status_code=302)
        raise
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/static/{filename}")
async def static_file(filename: str):
    if filename not in {"index.html", "app.js", "style.css", "lexmom-email.js", "lexmom-email.css", "lexmom-social.js", "lexmom-social.css"}:
        raise HTTPException(404, "Not found")
    return FileResponse(STATIC / filename, headers={"Cache-Control": "no-cache"})


@app.get("/api/agents")
async def agents(request: Request):
    await authorize(request)
    try:
        response = await upstream(request, "/api/agents")
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Agent list unavailable") from None
    imported = imported_workloads()
    imported_names = {row["module_name"] for row in imported}
    return [{**row, **public_config()} if row.get("module_name") == NAME else row
            for row in rows if row.get("module_name") not in imported_names] + imported


@app.get(BASE)
async def detail(request: Request):
    await authorize(request)
    return {**public_config(), "memory": load_memory(NAME)}


@app.get("/api/agents/{workload_name}")
async def imported_detail(request: Request, workload_name: str):
    await authorize(request)
    for row in imported_workloads():
        if row["module_name"] == workload_name:
            return row
    raise HTTPException(404, "Workload not found")


@app.get(BASE + "/dashboard-data")
async def data(request: Request):
    await authorize(request)
    return await asyncio.to_thread(dashboard)


@app.get(BASE + "/run-status")
async def status(request: Request):
    await authorize(request)
    return await asyncio.to_thread(run_status)


@app.get(BASE + "/artifacts/{run_id}/{filename}")
async def artifact(request: Request, run_id: str, filename: str):
    await authorize(request)
    path = resolve_research_artifact(run_id, filename)
    if path is None:
        raise HTTPException(404, "Research artifact not found")
    return FileResponse(path, filename=filename, headers={"Cache-Control": "private, no-store"})


def bounded_profile(payload):
    payload = dict(payload)
    payload.setdefault("deadline_seconds", 300)
    profile = validate_profile(payload, browser=True).model_dump()
    # A public UI cannot raise the worker's currently accepted operating bounds.
    caps = {"max_queries": 3, "max_llm_calls": 15, "max_verifications": 3,
            "deadline_seconds": 300, "max_candidates": 10, "target_count": 5,
            "budget_usd": 1.0}
    for field, maximum in caps.items():
        profile[field] = min(profile[field], maximum)
    profile.update(max_input_tokens=20000, max_output_tokens=3000, request_timeout=40, enable_verification=True)
    request = validate_request(profile)
    live_preflight(request)
    return request.model_dump(exclude={"unit_costs"})


@app.post(BASE + "/run")
async def run(request: Request):
    await authorize(request, write=True)
    body = await request.body()
    if len(body) > 32000:
        raise HTTPException(413, "Research profile is too large")
    try:
        if json.loads(body or b"{}") != {}:
            raise ValueError("Dashboard runs use saved server configuration")
        profile = bounded_profile(load_saved_profile())
    except (ValueError, TypeError):
        raise HTTPException(422, "Check the saved research JSON and provider configuration; dashboard overrides are disabled") from None
    # This provider snapshot is operational data, never a claim about future quota.
    provider = read_json(ROOT / "state/providers.json", {}).get("search", {})
    if not profile.get("seed_urls") and provider.get("remaining") == 0:
        raise HTTPException(503, "Search quota is exhausted. Update the saved research configuration or restore quota.")
    async with run_lock:
        if (await asyncio.to_thread(run_status))["status"] != "idle":
            raise HTTPException(409, "Research is already running")
        previous = read_json(ROOT / "state/status.json", {})
        _atomic_json(ROOT / "pilot.json", profile)
        try:
            await asyncio.to_thread(control, "start")
        except subprocess.SubprocessError:
            raise HTTPException(503, "Research worker could not be started") from None

    async def events():
        yield 'data: ' + json.dumps({"type": "step", "message": "Lexmom Sub Manager started the AWS research worker."}) + '\n\n'
        last_message = None
        for _ in range(360):
            snapshot = await asyncio.to_thread(run_status)
            current = snapshot["receipt"]
            if current.get("message") and current["message"] != last_message:
                last_message = current["message"]
                yield 'data: ' + json.dumps({"type": "step", "message": last_message}) + '\n\n'
            if snapshot["status"] == "idle" and current != previous and current.get("status") != "running":
                result = (await asyncio.to_thread(get_dashboard_data)).get("lastResult") or current
                yield 'data: ' + json.dumps({"type": "complete", "result": result}) + '\n\n'
                return
            if snapshot["status"] == "idle" and snapshot.get("serviceResult") not in {None, "success"}:
                yield 'data: ' + json.dumps({"type": "complete", "result": {"status": "failure", "error": "Worker stopped unexpectedly; inspect the preserved run."}}) + '\n\n'
                return
            yield ': waiting\n\n'
            await asyncio.sleep(1)
        yield 'data: ' + json.dumps({"type": "error", "message": "Status stream timed out. Refresh to reconnect to the worker."}) + '\n\n'
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post(BASE + "/stop")
async def stop(request: Request):
    await authorize(request, write=True)
    await asyncio.to_thread(control, "stop")
    return {"status": "stopping", "message": "Cancellation requested; completed research is preserved."}


@app.get("/api/agents/{workload_name}/run-status")
async def imported_status(request: Request, workload_name: str):
    row = await imported_detail(request, workload_name)
    return {"status": row["status"], "execution_enabled": False, "verified_at": row["verified_at"]}


@app.post("/api/agents/{workload_name}/run")
async def imported_run(request: Request, workload_name: str):
    await authorize(request, write=True)
    if workload_name not in IMPORTED_WORKLOADS:
        raise HTTPException(404, "Workload not found")
    raise HTTPException(409, "This workload is paused. Execution is disabled to prevent API spending.")


from agents.email_campaign_agent.api import register_routes as register_email_routes
register_email_routes(app, authorize)
from agents.social_media_posting_agent.api import register_routes as register_social_routes
register_social_routes(app, authorize)
from agents.prospect_research_agent.source_api import register_routes as register_source_routes
register_source_routes(app, authorize)
