"""Authenticated, bounded source tests shared by the local and AWS adapters."""
import asyncio
import threading
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .source_import import SourceImports
from .tools import SourceError


BASE = "/api/agents/lexmom_marketing_agent/source-imports"


def register_routes(app, authorize, state_directory=None):
    service, lock = None, threading.Lock()

    def imports():
        nonlocal service
        with lock:
            if service is None:
                root = state_directory() if callable(state_directory) else state_directory
                root = root or Path(__file__).resolve().parents[2] / "runtime-data/prospect_research_agent/source-imports"
                service = SourceImports(root)
        return service

    async def private(request, write=False):
        user = await authorize(request, write=write)
        if user.get("role") not in {"admin", "operator"}:
            raise HTTPException(403, "An operator account is required")

    def response(data):
        return JSONResponse(data, headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"})

    @app.get(BASE)
    async def latest(request: Request):
        await private(request)
        try:
            return response(await asyncio.to_thread(lambda: imports().latest()))
        except (ValueError, OSError):
            raise HTTPException(503, "Saved source test is unavailable; preserved state needs review") from None

    @app.get(BASE + "/{job_id}")
    async def status(job_id: str, request: Request):
        await private(request)
        try:
            return response(await asyncio.to_thread(lambda: imports().get(job_id)))
        except (ValueError, OSError):
            raise HTTPException(404, "Source test not found") from None

    @app.post(BASE)
    async def start(request: Request):
        await private(request, True)
        if len(await request.body()) > 4000:
            raise HTTPException(413, "Source request is too large")
        try:
            payload = await request.json()
            return response(await asyncio.to_thread(lambda: imports().start(payload)))
        except (ValueError, TypeError, SourceError):
            raise HTTPException(422, "Use a public source URL without credentials or unsupported queries. API field mappings and credentials belong in protected server configuration.") from None
        except RuntimeError:
            raise HTTPException(409, "A source test is already running") from None

    return imports
