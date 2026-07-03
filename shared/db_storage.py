import json
import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE_PATH = PROJECT_ROOT / "shared" / "agent_data.json"
STORE_PATH = Path(os.getenv("MENTESO_AGENT_DATA_FILE") or DEFAULT_STORE_PATH)
_LOCK = threading.RLock()
_SCHEMA_READY = False


def db_enabled():
    return True


def utc_now():
    return datetime.now(timezone.utc)


def _iso(value=None):
    value = value or utc_now()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def json_safe(value):
    try:
        json.dumps(value)
        return value
    except Exception:
        if isinstance(value, dict):
            return {str(k): json_safe(v) for k, v in value.items() if not callable(v)}
        if isinstance(value, (list, tuple)):
            return [json_safe(v) for v in value if not callable(v)]
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if callable(value):
            return None
        return str(value)


def _empty_store():
    return {
        "version": 1,
        "updated_at": _iso(),
        "agent_snapshots": {},
        "agent_runs": [],
        "agent_events": [],
        "agent_artifacts": [],
        "subagent_snapshots": {},
    }


def _load_store():
    if not STORE_PATH.exists():
        return _empty_store()
    try:
        with STORE_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return _empty_store()
    store = _empty_store()
    if isinstance(data, dict):
        store.update({key: data.get(key, store[key]) for key in store})
    return store


def _save_store(store):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    store["updated_at"] = _iso()
    # Compact dump (no indent / sort_keys) — pretty-printing a multi-MB store on
    # every event was burning seconds of CPU per write and stalling runs.
    payload = json.dumps(json_safe(store), ensure_ascii=True, separators=(",", ":"))
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(STORE_PATH.parent),
            delete=False,
            prefix=f".{STORE_PATH.name}.",
            suffix=".tmp",
        ) as handle:
            handle.write(payload)
            handle.write("\n")
            temp_name = handle.name
        # Windows os.replace fails with a PermissionError if the target is held
        # open by another handle/process. Retry briefly, then give up WITHOUT
        # leaving the temp file behind (orphaned temps previously piled up into
        # tens of GB and stalled every run).
        for attempt in range(5):
            try:
                Path(temp_name).replace(STORE_PATH)
                temp_name = None
                return
            except PermissionError:
                time.sleep(0.1 * (attempt + 1))
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink()
            except Exception:
                pass


@contextmanager
def connection():
    yield None


def ensure_schema():
    global _SCHEMA_READY
    with _LOCK:
        if not STORE_PATH.exists():
            _save_store(_empty_store())
        _SCHEMA_READY = True
    return True


def _snapshot_key(agent_key, workspace_id=""):
    return f"{str(agent_key)}::{str(workspace_id or '')}"


def _subagent_key(agent_key, workspace_id="", subagent_name=""):
    return f"{str(agent_key)}::{str(workspace_id or '')}::{str(subagent_name)}"


def _limited_append(items, item, max_items=5000):
    items.append(item)
    if len(items) > max_items:
        del items[: len(items) - max_items]


def upsert_agent_snapshot(agent_key, workspace_id="", agent_name="", dashboard=None, memory=None, stats=None):
    ensure_schema()
    key = _snapshot_key(agent_key, workspace_id)
    with _LOCK:
        store = _load_store()
        store["agent_snapshots"][key] = {
            "agent_key": str(agent_key),
            "workspace_id": str(workspace_id or ""),
            "agent_name": str(agent_name or agent_key),
            "dashboard_json": json_safe(dashboard or {}),
            "memory_json": json_safe(memory or {}),
            "stats_json": json_safe(stats or {}),
            "updated_at": _iso(),
        }
        _save_store(store)
    return True


def insert_agent_run(agent_key, workspace_id="", run_id="", task="", status="", result=None, summary=None, execution_time=None, started_at=None, finished_at=None):
    ensure_schema()
    run_id = str(run_id or uuid.uuid4().hex)
    result = result or {}
    summary = summary if summary is not None else (result.get("summary") if isinstance(result, dict) else {})
    # Never persist the heavy per-row `results` (thousands of rows with emails)
    # into the run history — that grew the store to 100+ MB and made every
    # subsequent write rewrite the whole file. Keep only lightweight metadata.
    if isinstance(result, dict):
        light_result = {k: v for k, v in result.items() if k not in ("results", "rows")}
    else:
        light_result = {}
    with _LOCK:
        store = _load_store()
        _limited_append(
            store["agent_runs"],
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "agent_key": str(agent_key),
                "workspace_id": str(workspace_id or ""),
                "task": str(task or ""),
                "status": str(status or ""),
                "started_at": _iso(started_at) if started_at else None,
                "finished_at": _iso(finished_at or utc_now()),
                "execution_time": execution_time,
                "summary_json": json_safe(summary or {}),
                "result_json": json_safe(light_result),
                "created_at": _iso(),
            },
            max_items=300,
        )
        _save_store(store)
    return True


def insert_agent_event(agent_key, workspace_id="", run_id="", event_type="step", message="", payload=None):
    ensure_schema()
    with _LOCK:
        store = _load_store()
        _limited_append(
            store["agent_events"],
            {
                "id": len(store["agent_events"]) + 1,
                "run_id": str(run_id or ""),
                "agent_key": str(agent_key),
                "workspace_id": str(workspace_id or ""),
                "event_type": str(event_type or "step"),
                "message": str(message or "")[:4000],
                "payload_json": json_safe(payload or {}),
                "created_at": _iso(),
            },
        )
        _save_store(store)
    return True


def insert_artifact(agent_key, workspace_id="", run_id="", artifact_type="", name="", url="", path="", payload=None):
    ensure_schema()
    with _LOCK:
        store = _load_store()
        _limited_append(
            store["agent_artifacts"],
            {
                "id": len(store["agent_artifacts"]) + 1,
                "agent_key": str(agent_key),
                "workspace_id": str(workspace_id or ""),
                "run_id": str(run_id or ""),
                "artifact_type": str(artifact_type or ""),
                "name": str(name or ""),
                "url": str(url or ""),
                "path": str(path or ""),
                "payload_json": json_safe(payload or {}),
                "created_at": _iso(),
            },
        )
        _save_store(store)
    return True


def upsert_subagent_snapshot(agent_key, subagent_name, workspace_id="", status="", stats=None, payload=None):
    ensure_schema()
    key = _subagent_key(agent_key, workspace_id, subagent_name)
    with _LOCK:
        store = _load_store()
        store["subagent_snapshots"][key] = {
            "agent_key": str(agent_key),
            "workspace_id": str(workspace_id or ""),
            "subagent_name": str(subagent_name),
            "status": str(status or ""),
            "stats_json": json_safe(stats or {}),
            "payload_json": json_safe(payload or {}),
            "updated_at": _iso(),
        }
        _save_store(store)
    return True


def latest_agent_runs(agent_key, workspace_id="", limit=10):
    ensure_schema()
    with _LOCK:
        runs = [
            run for run in _load_store()["agent_runs"]
            if run.get("agent_key") == str(agent_key) and run.get("workspace_id") == str(workspace_id or "")
        ]
    runs.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return runs[: int(limit)]


def snapshot(agent_key, workspace_id=""):
    ensure_schema()
    with _LOCK:
        return _load_store()["agent_snapshots"].get(_snapshot_key(agent_key, workspace_id))
