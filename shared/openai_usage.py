"""Server-side OpenAI organization usage and cost reporting.

The admin key is read only from the process environment.  This module never
returns it (or a hash of it) to API callers.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


OPENAI_API_BASE = "https://api.openai.com/v1"
ALLOWED_DAY_RANGES = {1, 7, 30, 90}
CACHE_TTL_SECONDS = 120
HIGH_CONSUMPTION_SHARE = 0.50

USAGE_ENDPOINTS = {
    "completions": {
        "path": "/organization/usage/completions",
        "label": "Completions / Responses",
        "group_by": ["api_key_id", "project_id", "model"],
    },
    "embeddings": {
        "path": "/organization/usage/embeddings",
        "label": "Embeddings",
        "group_by": ["api_key_id", "project_id", "model"],
    },
    "images": {
        "path": "/organization/usage/images",
        "label": "Images",
        "group_by": ["api_key_id", "project_id", "model", "source"],
    },
    "audio_speeches": {
        "path": "/organization/usage/audio_speeches",
        "label": "Text to speech",
        "group_by": ["api_key_id", "project_id", "model"],
    },
    "audio_transcriptions": {
        "path": "/organization/usage/audio_transcriptions",
        "label": "Transcriptions",
        "group_by": ["api_key_id", "project_id", "model"],
    },
    "moderations": {
        "path": "/organization/usage/moderations",
        "label": "Moderations",
        "group_by": ["api_key_id", "project_id", "model"],
    },
    "vector_stores": {
        "path": "/organization/usage/vector_stores",
        "label": "Vector storage",
        "group_by": ["project_id"],
    },
    "code_interpreter_sessions": {
        "path": "/organization/usage/code_interpreter_sessions",
        "label": "Code interpreter",
        "group_by": ["project_id"],
    },
    "file_search_calls": {
        "path": "/organization/usage/file_search_calls",
        "label": "File search",
        "group_by": ["api_key_id", "project_id"],
    },
    "web_search_calls": {
        "path": "/organization/usage/web_search_calls",
        "label": "Web search",
        "group_by": ["api_key_id", "project_id", "model"],
    },
}


class OpenAIUsageError(RuntimeError):
    """A safe-to-display error raised while reading organization metrics."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class OpenAIAdminClient:
    def __init__(self, api_key: str, timeout_seconds: int = 25):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = OPENAI_API_BASE

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                params=params or {},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise OpenAIUsageError("OpenAI usage service could not be reached.") from exc

        if response.status_code in {401, 403}:
            raise OpenAIUsageError(
                "The configured key cannot read organization usage. Use an OpenAI Admin API key created by an organization owner.",
                status_code=503,
            )
        if response.status_code == 429:
            raise OpenAIUsageError("OpenAI usage reporting is temporarily rate limited. Please retry shortly.", 503)
        if not response.ok:
            request_id = response.headers.get("x-request-id", "")
            suffix = f" Request ID: {request_id}." if request_id else ""
            raise OpenAIUsageError(f"OpenAI usage reporting returned HTTP {response.status_code}.{suffix}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenAIUsageError("OpenAI usage reporting returned an invalid response.") from exc
        return payload if isinstance(payload, dict) else {}

    def get_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Read every page from an OpenAI list or time-bucket endpoint."""
        query = dict(params or {})
        records: list[dict[str, Any]] = []
        seen_pages: set[str] = set()
        for _ in range(100):
            payload = self._get(path, query)
            data = payload.get("data")
            if isinstance(data, list):
                records.extend(item for item in data if isinstance(item, dict))
            if not payload.get("has_more"):
                break
            next_page = str(payload.get("next_page") or payload.get("last_id") or "").strip()
            if not next_page or next_page in seen_pages:
                break
            seen_pages.add(next_page)
            query["page"] = next_page
            if "next_page" not in payload and payload.get("last_id"):
                query.pop("page", None)
                query["after"] = next_page
        return records


_CACHE: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> int:
    return int(_number(value))


def _day_label(timestamp: Any) -> str:
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return "Unknown"


def _display_id(value: str | None, fallback: str) -> str:
    value = str(value or "").strip()
    return value if value else fallback


def _usage_metrics(result: dict[str, Any], family: str) -> dict[str, int]:
    requests_count = _integer(result.get("num_model_requests"))
    if family in {"file_search_calls", "web_search_calls"}:
        requests_count = _integer(result.get("num_requests")) or requests_count
    elif family == "code_interpreter_sessions":
        requests_count = _integer(result.get("num_sessions"))

    input_tokens = _integer(result.get("input_tokens"))
    output_tokens = _integer(result.get("output_tokens"))
    return {
        "requests": requests_count,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
        "images": _integer(result.get("images")),
        "seconds": _integer(result.get("seconds")),
        "characters": _integer(result.get("characters")),
        "storageBytes": _integer(result.get("usage_bytes")),
        "sessions": _integer(result.get("num_sessions")),
    }


def _add_metrics(target: dict[str, Any], metrics: dict[str, int]) -> None:
    for field, value in metrics.items():
        target[field] = _integer(target.get(field)) + value


def _key_name(key_id: str, key_metadata: dict[str, dict[str, Any]]) -> str:
    metadata = key_metadata.get(key_id, {})
    name = str(metadata.get("name") or "").strip()
    if name:
        return name
    if key_id == "unattributed":
        return "Unattributed usage"
    return f"API key …{key_id[-8:]}" if len(key_id) > 8 else key_id


def _project_name(project_id: str, project_metadata: dict[str, dict[str, Any]]) -> str:
    metadata = project_metadata.get(project_id, {})
    name = str(metadata.get("name") or "").strip()
    if name:
        return name
    if project_id == "unattributed":
        return "Unattributed project"
    return project_id


def build_dashboard_payload(
    *,
    days: int,
    start_time: int,
    end_time: int,
    costs: list[dict[str, Any]],
    usage: dict[str, list[dict[str, Any]]],
    key_metadata: dict[str, dict[str, Any]] | None = None,
    project_metadata: dict[str, dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    key_metadata = key_metadata or {}
    project_metadata = project_metadata or {}
    warning_list = list(warnings or [])

    cost_by_day: dict[str, float] = defaultdict(float)
    cost_by_key: dict[str, float] = defaultdict(float)
    cost_by_project: dict[str, float] = defaultdict(float)
    cost_by_line: dict[str, float] = defaultdict(float)
    key_projects: dict[str, set[str]] = defaultdict(set)
    currency = "usd"

    for bucket in costs:
        day = _day_label(bucket.get("start_time"))
        for result in bucket.get("results") or []:
            if not isinstance(result, dict):
                continue
            amount = result.get("amount") if isinstance(result.get("amount"), dict) else {}
            value = _number(amount.get("value"))
            currency = str(amount.get("currency") or currency).lower()
            key_id = _display_id(result.get("api_key_id"), "unattributed")
            project_id = _display_id(result.get("project_id"), "unattributed")
            line_item = _display_id(result.get("line_item"), "Other OpenAI usage")
            cost_by_day[day] += value
            cost_by_key[key_id] += value
            cost_by_project[project_id] += value
            cost_by_line[line_item] += value
            key_projects[key_id].add(project_id)

    totals = {
        "requests": 0,
        "inputTokens": 0,
        "outputTokens": 0,
        "totalTokens": 0,
    }
    usage_by_key: dict[str, dict[str, Any]] = defaultdict(dict)
    usage_by_model: dict[str, dict[str, Any]] = defaultdict(dict)
    family_rows: list[dict[str, Any]] = []
    usage_projects: set[str] = set()

    for family, config in USAGE_ENDPOINTS.items():
        family_total: dict[str, Any] = {}
        for bucket in usage.get(family, []):
            for result in bucket.get("results") or []:
                if not isinstance(result, dict):
                    continue
                metrics = _usage_metrics(result, family)
                _add_metrics(family_total, metrics)
                key_id = _display_id(result.get("api_key_id"), "unattributed")
                project_id = _display_id(result.get("project_id"), "unattributed")
                model = str(result.get("model") or "").strip()
                _add_metrics(usage_by_key[key_id], metrics)
                if model:
                    _add_metrics(usage_by_model[model], metrics)
                key_projects[key_id].add(project_id)
                usage_projects.add(project_id)
        for field in totals:
            totals[field] += _integer(family_total.get(field))
        family_rows.append({
            "id": family,
            "name": config["label"],
            **{field: _integer(family_total.get(field)) for field in (
                "requests", "inputTokens", "outputTokens", "totalTokens",
                "images", "seconds", "characters", "storageBytes", "sessions",
            )},
        })

    all_key_ids = set(cost_by_key) | set(usage_by_key)
    total_cost = sum(cost_by_key.values())
    api_keys = []
    for key_id in all_key_ids:
        metrics = usage_by_key.get(key_id, {})
        project_ids = sorted(key_projects.get(key_id) or {"unattributed"})
        metadata = key_metadata.get(key_id, {})
        owner = metadata.get("owner") if isinstance(metadata.get("owner"), dict) else {}
        api_keys.append({
            "id": key_id,
            "name": _key_name(key_id, key_metadata),
            "redactedValue": str(metadata.get("redacted_value") or ""),
            "ownerType": str(owner.get("type") or ""),
            "projects": [
                {"id": project_id, "name": _project_name(project_id, project_metadata)}
                for project_id in project_ids
            ],
            "cost": round(cost_by_key.get(key_id, 0.0), 6),
            "share": round((cost_by_key.get(key_id, 0.0) / total_cost), 6) if total_cost else 0,
            **{field: _integer(metrics.get(field)) for field in (
                "requests", "inputTokens", "outputTokens", "totalTokens",
            )},
        })
    api_keys.sort(key=lambda row: (row["cost"], row["requests"], row["totalTokens"]), reverse=True)

    range_start = datetime.fromtimestamp(start_time, timezone.utc).date()
    trend = []
    for offset in range(days + 1):
        current = range_start + timedelta(days=offset)
        if current > datetime.fromtimestamp(end_time, timezone.utc).date():
            break
        label = current.isoformat()
        trend.append({"date": label, "cost": round(cost_by_day.get(label, 0.0), 6)})

    projects = [
        {
            "id": project_id,
            "name": _project_name(project_id, project_metadata),
            "cost": round(value, 6),
            "share": round(value / total_cost, 6) if total_cost else 0,
        }
        for project_id, value in cost_by_project.items()
    ]
    projects.sort(key=lambda row: row["cost"], reverse=True)

    line_items = [
        {
            "name": name,
            "cost": round(value, 6),
            "share": round(value / total_cost, 6) if total_cost else 0,
        }
        for name, value in cost_by_line.items()
    ]
    line_items.sort(key=lambda row: row["cost"], reverse=True)

    models = [
        {"name": name, **{field: _integer(metrics.get(field)) for field in (
            "requests", "inputTokens", "outputTokens", "totalTokens",
        )}}
        for name, metrics in usage_by_model.items()
        if any(_integer(metrics.get(field)) for field in ("requests", "totalTokens"))
    ]
    models.sort(key=lambda row: (row["totalTokens"], row["requests"]), reverse=True)
    family_rows.sort(key=lambda row: (row["totalTokens"], row["requests"], row["storageBytes"]), reverse=True)

    alerts = []
    if api_keys and api_keys[0]["share"] >= HIGH_CONSUMPTION_SHARE and total_cost > 0:
        top = api_keys[0]
        alerts.append({
            "level": "warning",
            "title": "High API-key concentration",
            "message": f"{top['name']} accounts for {top['share'] * 100:.1f}% of spend in this period.",
        })
    if projects and projects[0]["share"] >= HIGH_CONSUMPTION_SHARE and total_cost > 0:
        top = projects[0]
        alerts.append({
            "level": "warning",
            "title": "High project concentration",
            "message": f"{top['name']} accounts for {top['share'] * 100:.1f}% of spend in this period.",
        })
    if not alerts:
        alerts.append({
            "level": "ok",
            "title": "No concentration warning",
            "message": "No single API key or project is above 50% of measured spend.",
        })

    return {
        "configured": True,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "range": {"days": days, "startTime": start_time, "endTime": end_time},
        "currency": currency,
        "summary": {
            "cost": round(total_cost, 6),
            **totals,
            "activeKeys": len([row for row in api_keys if row["cost"] or row["requests"] or row["totalTokens"]]),
            "activeProjects": len((set(cost_by_project) | usage_projects) - {"unattributed"}),
            "topConsumer": api_keys[0]["name"] if api_keys else "No usage",
            "topConsumerShare": api_keys[0]["share"] if api_keys else 0,
        },
        "trend": trend,
        "apiKeys": api_keys,
        "projects": projects,
        "costDrivers": line_items,
        "models": models,
        "apiFamilies": family_rows,
        "alerts": alerts,
        "warnings": warning_list,
    }


def _metadata_maps(client: OpenAIAdminClient) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    warnings: list[str] = []
    keys: dict[str, dict[str, Any]] = {}
    projects: dict[str, dict[str, Any]] = {}
    try:
        for item in client.get_all("/organization/admin_api_keys", {"limit": 100}):
            item_id = str(item.get("id") or "").strip()
            if item_id:
                keys[item_id] = item
    except OpenAIUsageError:
        warnings.append("API key names could not be loaded; usage IDs are shown instead.")
    try:
        for item in client.get_all("/organization/projects", {"limit": 100}):
            item_id = str(item.get("id") or "").strip()
            if item_id:
                projects[item_id] = item
    except OpenAIUsageError:
        warnings.append("Project names could not be loaded; project IDs are shown instead.")
    return keys, projects, warnings


def _fetch_dashboard(api_key: str, days: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    end_time = int(now.timestamp())
    start_time = int((now - timedelta(days=days)).timestamp())
    client = OpenAIAdminClient(api_key)
    common = {
        "start_time": start_time,
        "end_time": end_time,
        "bucket_width": "1d",
        "limit": min(days + 1, 31),
    }

    tasks: dict[Any, tuple[str, str]] = {}
    results: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="openai-usage") as executor:
        cost_params = {**common, "limit": min(days + 1, 180), "group_by": ["project_id", "api_key_id", "line_item"]}
        tasks[executor.submit(client.get_all, "/organization/costs", cost_params)] = ("costs", "Costs")
        for family, config in USAGE_ENDPOINTS.items():
            params = {**common, "group_by": config["group_by"]}
            tasks[executor.submit(client.get_all, config["path"], params)] = (family, config["label"])
        tasks[executor.submit(_metadata_maps, client)] = ("metadata", "Metadata")

        key_metadata: dict[str, dict[str, Any]] = {}
        project_metadata: dict[str, dict[str, Any]] = {}
        fatal_cost_error: OpenAIUsageError | None = None
        for future in as_completed(tasks):
            key, label = tasks[future]
            try:
                value = future.result()
                if key == "metadata":
                    key_metadata, project_metadata, metadata_warnings = value
                    warnings.extend(metadata_warnings)
                else:
                    results[key] = value
            except OpenAIUsageError as exc:
                if key == "costs":
                    fatal_cost_error = exc
                else:
                    warnings.append(f"{label} metrics are temporarily unavailable.")

    if fatal_cost_error:
        raise fatal_cost_error
    return build_dashboard_payload(
        days=days,
        start_time=start_time,
        end_time=end_time,
        costs=results.get("costs", []),
        usage={family: results.get(family, []) for family in USAGE_ENDPOINTS},
        key_metadata=key_metadata,
        project_metadata=project_metadata,
        warnings=warnings,
    )


def get_openai_usage_dashboard(days: int = 7, force_refresh: bool = False) -> dict[str, Any]:
    if days not in ALLOWED_DAY_RANGES:
        raise OpenAIUsageError("The requested reporting range is not supported.", 400)

    api_key = str(os.getenv("OPENAI_ADMIN_KEY") or "").strip()
    if not api_key:
        return {
            "configured": False,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "range": {"days": days},
            "setup": {
                "envVar": "OPENAI_ADMIN_KEY",
                "message": "Add an OpenAI Admin API key to the server environment, then restart the dashboard service.",
            },
        }

    fingerprint = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
    cache_key = (days, fingerprint)
    now = time.monotonic()
    if not force_refresh:
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and now - cached[0] < CACHE_TTL_SECONDS:
                return {**cached[1], "cached": True}

    payload = _fetch_dashboard(api_key, days)
    with _CACHE_LOCK:
        _CACHE[cache_key] = (time.monotonic(), payload)
        for existing_key in list(_CACHE):
            if existing_key[1] != fingerprint:
                _CACHE.pop(existing_key, None)
    return {**payload, "cached": False}
