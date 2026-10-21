"""Local Ollama vision transport; no cloud fallback or document transformations."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import struct
from pathlib import Path
from urllib.parse import urlsplit

import requests

from shared.config import get_env


def _integer(name, default, minimum, maximum):
    try:
        value = int(get_env(name) or default)
        if not minimum <= value <= maximum:
            raise ValueError
        return value
    except (TypeError, ValueError):
        raise ValueError(f"ollama_invalid_{name.lower()}") from None


def settings():
    url = (get_env("PCT_OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                 and parsed.port is not None and not parsed.username and not parsed.password
                 and not parsed.path and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("ollama_requires_loopback_url")
    model = (get_env("PCT_OLLAMA_MODEL") or "qwen3.5:4b").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,150}", model) or "cloud" in model.lower():
        raise ValueError("ollama_requires_local_model")
    if ":" not in model:
        model += ":latest"
    digest = (get_env("PCT_OLLAMA_MODEL_DIGEST") or "").strip()
    if digest and not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("ollama_invalid_model_digest")
    return {"base_url": url, "model": model, "expected_digest": digest,
            "timeout": _integer("PCT_OLLAMA_TIMEOUT_SECONDS", 1800, 60, 7200),
            "num_ctx": _integer("PCT_OLLAMA_CONTEXT_LENGTH", 65536, 8192, 131072),
            "num_thread": _integer("PCT_OLLAMA_NUM_THREADS", 4, 1, 64),
            "num_predict": 7000}


def _json_request(config, route, payload=None, timeout=15):
    # Ignore machine proxy/netrc credentials for this loopback-only provider.
    try:
        with requests.Session() as session:
            session.trust_env = False
            kwargs = {"timeout": (10, timeout), "allow_redirects": False}
            if payload is None:
                response = session.get(config["base_url"] + route, **kwargs)
            else:
                response = session.post(config["base_url"] + route, json=payload, **kwargs)
            if response.status_code != 200:
                raise RuntimeError(f"ollama_http_{response.status_code}")
            result = response.json()
    except requests.Timeout:
        raise RuntimeError("ollama_timeout") from None
    except requests.RequestException:
        raise RuntimeError("ollama_unreachable") from None
    except (ValueError, TypeError):
        raise RuntimeError("ollama_invalid_json") from None
    if not isinstance(result, dict) or result.get("error"):
        raise RuntimeError("ollama_invalid_response")
    return result


def model_identity(config=None):
    config = config or settings()
    listing = _json_request(config, "/api/tags")
    models = listing.get("models")
    if not isinstance(models, list) or any(not isinstance(item, dict) for item in models):
        raise RuntimeError("ollama_invalid_model_metadata")
    entry = next((item for item in models if item.get("name") == config["model"]), None)
    if entry is None:
        raise RuntimeError("ollama_model_not_installed")
    digest = entry.get("digest", "")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise RuntimeError("ollama_model_digest_missing")
    if config["expected_digest"] and digest != config["expected_digest"]:
        raise RuntimeError("ollama_model_digest_changed")
    details = _json_request(config, "/api/show", {"model": config["model"]})
    if entry.get("remote_model") or entry.get("remote_host") or details.get("remote_model") or details.get("remote_host"):
        raise RuntimeError("ollama_cloud_model_forbidden")
    if not isinstance(details.get("capabilities"), list) or "vision" not in details["capabilities"]:
        raise RuntimeError("ollama_vision_required")
    # The context budget below uses Qwen3.5's 16px patches / 2x spatial merge.
    if not isinstance(details.get("details"), dict) or details["details"].get("family") != "qwen35":
        raise RuntimeError("ollama_model_family_not_validated")
    return {"provider": "ollama", "model": config["model"], "digest": digest}


def validate_configuration(check_api=False):
    config = settings()
    if check_api:
        try:
            model_identity(config)
        except RuntimeError as exc:
            raise ValueError(str(exc)) from None


def cache_material():
    config = settings()
    return {**model_identity(config), "context_length": config["num_ctx"],
            "max_output_tokens": config["num_predict"], "thinking": False,
            "transport_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def _image_budget(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 24:
        raise RuntimeError("ollama_invalid_page_image")
    width, height = struct.unpack(">II", data[16:24])
    if not width or not height:
        raise RuntimeError("ollama_invalid_page_image")
    # Round UP to complete merged patches; add room for image delimiters.
    return math.ceil(width / 32) * math.ceil(height / 32) + 32


def request(pages, instruction, context, schema):
    config = settings()
    model_identity(config)  # Also refuses a replaced pinned model during a run.
    public_context = {key: value for key, value in (context or {}).items()
                      if not str(key).startswith("_")}
    messages = [{"role": "system", "content": instruction},
                {"role": "user", "content": "Filing metadata (context only, not proof): "
                 + json.dumps(public_context)}]
    for page, data in pages:
        messages.append({"role": "user", "content": f"Original PDF page {page}",
                         "images": [base64.b64encode(data).decode("ascii")]})
    # Do not silently shrink/crop pages or let a small context drop early pages.
    # UTF-8 byte length is deliberately conservative for text/token budgeting.
    text_bytes = sum(len(m["content"].encode("utf-8")) for m in messages)
    budget = text_bytes + len(json.dumps(schema).encode("utf-8")) + 1024
    budget += sum(_image_budget(data) for _, data in pages) + config["num_predict"]
    if budget > config["num_ctx"]:
        raise RuntimeError("ollama_context_capacity")
    payload = {"model": config["model"], "messages": messages, "stream": False,
               "think": False, "format": schema, "keep_alive": "5m",
               "options": {"temperature": 0, "seed": 42, "num_ctx": config["num_ctx"],
                           "num_predict": config["num_predict"], "num_thread": config["num_thread"]}}
    body = _json_request(config, "/api/chat", payload, timeout=config["timeout"])
    if body.get("done") is not True or body.get("done_reason") != "stop":
        raise RuntimeError("ollama_incomplete_response")
    message = body.get("message")
    if not isinstance(message, dict) or message.get("tool_calls") or not isinstance(message.get("content"), str):
        raise RuntimeError("ollama_missing_output")
    if not message["content"].strip():
        raise RuntimeError("ollama_missing_output")
    return message["content"]
