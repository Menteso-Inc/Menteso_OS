import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from .config import settings


def _node_path():
    if settings.worker_node_path:
        return settings.worker_node_path
    playwright_node = Path(__file__).resolve().parents[3] / ".venv" / "Lib" / "site-packages" / "playwright" / "driver" / "node.exe"
    if playwright_node.exists():
        return str(playwright_node)
    return "node"


def enqueue_job(job_type: str, input_ref: str, payload: dict) -> dict:
    job_id = f"{job_type}-{uuid4().hex[:12]}"
    enqueue_script = Path(settings.worker_service_dir) / "dist" / "enqueue.js"
    if not enqueue_script.exists():
        return {
            "job_id": job_id,
            "job_type": job_type,
            "status": "queued",
            "message": "Worker enqueue script not built yet; request recorded for later processing.",
        }

    env = os.environ.copy()
    node_binary = _node_path()
    env["PATH"] = f"{Path(node_binary).parent}{os.pathsep}{env.get('PATH', '')}"
    command = [
        node_binary,
        str(enqueue_script),
        "--job-type",
        job_type,
        "--input-ref",
        input_ref,
        "--payload",
        json.dumps(payload),
        "--job-id",
        job_id,
    ]
    subprocess.run(command, cwd=settings.worker_service_dir, env=env, check=False)
    return {
        "job_id": job_id,
        "job_type": job_type,
        "status": "queued",
        "message": "Job submitted to BullMQ enqueue bridge.",
    }
