"""
Menteso Virtual Office — Web Server
FastAPI backend serving the agent dashboard and API endpoints.
"""
import sys
import os
import json
import asyncio
import queue
import threading
import shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from shared.agent_registry import discover_agents, get_agent_runner
from shared.memory import load_memory
from agents.pct_agent.scraper import fetch_wipo_gazettes_async

app = FastAPI(title="Menteso Virtual Office")
RUN_CONTROLS = {}


def _get_run_status(name: str):
    control = RUN_CONTROLS.get(name)
    if not control:
        return {"status": "idle"}

    thread = control.get("thread")
    stop_event = control.get("stop_event")
    if thread and thread.is_alive():
        return {
            "status": "stopping" if stop_event and stop_event.is_set() else "running",
        }

    RUN_CONTROLS.pop(name, None)
    return {"status": "idle"}

# Directories
PROJECT_DIR = Path(__file__).parent
STATIC_DIR = PROJECT_DIR / "static"
UPLOADS_DIR = PROJECT_DIR / "uploads"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
WIPO_GAZETTES_CACHE = STATIC_DIR / "wipo_gazettes_cache.json"
UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _read_wipo_gazettes_cache():
    if not WIPO_GAZETTES_CACHE.exists():
        return []
    try:
        with open(WIPO_GAZETTES_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        options = data.get("options", [])
        return options if isinstance(options, list) else []
    except Exception:
        return []


def _write_wipo_gazettes_cache(options):
    payload = {"options": options}
    with open(WIPO_GAZETTES_CACHE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


# ---------------------------------------------------------------------------
# Root — serve dashboard HTML
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = STATIC_DIR / "index.html"
    with open(html_path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# API — List agents
# ---------------------------------------------------------------------------
@app.get("/api/agents")
async def list_agents():
    agents = discover_agents()
    result = []
    for a in agents:
        module_name = a.get("module_name", "")
        memory = load_memory(module_name)
        result.append({
            **a,
            "stats": memory.get("stats", {}),
            "learning_count": len(memory.get("learnings", [])),
        })
    return result


# ---------------------------------------------------------------------------
# API — Agent detail
# ---------------------------------------------------------------------------
@app.get("/api/agents/{name}")
async def agent_detail(name: str):
    agents = discover_agents()
    agent = next((a for a in agents if a["module_name"] == name), None)
    if not agent:
        return JSONResponse({"error": "Agent not found"}, status_code=404)

    memory = load_memory(name)
    return {
        **agent,
        "memory": memory,
    }


# ---------------------------------------------------------------------------
# API — Upload file for agent
# ---------------------------------------------------------------------------
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file (Excel, etc.) and return the saved path."""
    safe_name = file.filename.replace(" ", "_")
    save_path = UPLOADS_DIR / safe_name

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "filename": safe_name,
        "path": str(save_path),
        "size": len(content),
    }


# ---------------------------------------------------------------------------
# API — Download output file
# ---------------------------------------------------------------------------
@app.get("/api/download/{filename}")
async def download_file(filename: str):
    file_path = OUTPUTS_DIR / filename
    if not file_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(
        str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
# API — WIPO gazette options
# ---------------------------------------------------------------------------
@app.get("/api/wipo/gazettes")
async def list_wipo_gazettes():
    try:
        gazettes = await fetch_wipo_gazettes_async()
        _write_wipo_gazettes_cache(gazettes)
        return {"options": gazettes}
    except Exception as e:
        cached = _read_wipo_gazettes_cache()
        if cached:
            return {"options": cached, "cached": True}
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# API — Pipeline progress (for page refreshes during long runs)
# ---------------------------------------------------------------------------
@app.get("/api/agents/{name}/progress")
async def agent_progress(name: str):
    """Return current progress from the latest progress JSONL file."""
    import json as _json
    candidates = sorted(OUTPUTS_DIR.glob("pct_progress_*.jsonl"), reverse=True)
    if not candidates:
        return {"status": "no_progress"}
    path = candidates[0]
    try:
        meta = None
        completed = 0
        found = 0
        not_found = 0
        errors = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                obj = _json.loads(line.strip())
                if obj.get("_meta"):
                    meta = obj
                    continue
                completed += 1
                s = obj.get("status", "")
                if s == "found":
                    found += 1
                elif s == "not_found":
                    not_found += 1
                else:
                    errors += 1
        return {
            "status": "in_progress" if meta else "unknown",
            "file": path.name,
            "total": meta.get("total", 0) if meta else 0,
            "completed": completed,
            "found": found,
            "not_found": not_found,
            "errors": errors,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/agents/{name}/run-status")
async def agent_run_status(name: str):
    return _get_run_status(name)


# ---------------------------------------------------------------------------
# API — Run agent (SSE stream) — supports input_data via query params
# ---------------------------------------------------------------------------
@app.get("/api/agents/{name}/run")
async def run_agent_sse(
    name: str,
    file_path: str = None,
    mode: str = None,
    gazette: str = None,
):
    agents = discover_agents()
    agent = next((a for a in agents if a["module_name"] == name), None)
    if not agent:
        return JSONResponse({"error": "Agent not found"}, status_code=404)

    # Build input_data from query params
    input_data = {}
    if file_path:
        input_data["file_path"] = file_path
    if mode:
        input_data["mode"] = mode
    if gazette:
        input_data["gazette"] = gazette

    status = _get_run_status(name)
    if status["status"] != "idle":
        msg = "Agent is stopping, please wait" if status["status"] == "stopping" else "Agent is already running"
        return JSONResponse({"error": msg, "status": status["status"]}, status_code=409)

    msg_queue = queue.Queue()
    stop_event = threading.Event()
    control = {"stop_event": stop_event, "thread": None, "interruptors": []}
    input_data["stop_requested"] = stop_event.is_set

    def register_stop_handler(handler):
        if callable(handler):
            control["interruptors"].append(handler)

    input_data["register_stop_handler"] = register_stop_handler

    def on_step(message):
        if isinstance(message, dict):
            msg_queue.put(json.dumps(message))
        else:
            msg_queue.put(json.dumps({"type": "step", "message": message}))

    def worker():
        try:
            runner = get_agent_runner(name)
            result = runner(input_data=input_data or None, on_step=on_step)
            msg_queue.put(json.dumps({"type": "complete", "result": result}))
        except Exception as e:
            msg_queue.put(json.dumps({"type": "error", "message": str(e)}))
        finally:
            RUN_CONTROLS.pop(name, None)
            msg_queue.put(None)

    thread = threading.Thread(target=worker, daemon=True)
    control["thread"] = thread
    RUN_CONTROLS[name] = control
    thread.start()

    async def event_stream():
        while True:
            try:
                msg = msg_queue.get(timeout=0.05)
            except queue.Empty:
                yield ": keepalive\n\n"
                await asyncio.sleep(0.05)
                continue
            if msg is None:
                break
            yield f"data: {msg}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/agents/{name}/stop")
async def stop_agent_run(name: str):
    control = RUN_CONTROLS.get(name)
    if not control or not control.get("thread") or not control["thread"].is_alive():
        return JSONResponse({"error": "Agent is not running"}, status_code=409)

    control["stop_event"].set()
    interrupt_sent = 0
    for interruptor in list(control.get("interruptors", [])):
        try:
            interruptor()
            interrupt_sent += 1
        except Exception:
            pass
    return {"status": "stop_requested", "interrupt_sent": interrupt_sent}


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
