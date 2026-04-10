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

app = FastAPI(title="Menteso Virtual Office")

# Directories
PROJECT_DIR = Path(__file__).parent
STATIC_DIR = PROJECT_DIR / "static"
UPLOADS_DIR = PROJECT_DIR / "uploads"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
# API — Run agent (SSE stream) — supports input_data via query params
# ---------------------------------------------------------------------------
@app.get("/api/agents/{name}/run")
async def run_agent_sse(name: str, file_path: str = None, mode: str = None):
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

    msg_queue = queue.Queue()

    def on_step(message):
        msg_queue.put(json.dumps({"type": "step", "message": message}))

    def worker():
        try:
            runner = get_agent_runner(name)
            result = runner(input_data=input_data or None, on_step=on_step)
            msg_queue.put(json.dumps({"type": "complete", "result": result}))
        except Exception as e:
            msg_queue.put(json.dumps({"type": "error", "message": str(e)}))
        finally:
            msg_queue.put(None)

    thread = threading.Thread(target=worker, daemon=True)
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


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
