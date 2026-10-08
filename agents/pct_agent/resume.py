"""Validated, local handoffs retain row identity and verified contact evidence."""
import hashlib
import json
from pathlib import Path

from shared.config import get_env
from . import ai_verifier as ai, contact_policy as policy


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def policy_fingerprint():
    # Scheduling changes can retain these results only when the contact rules,
    # model, evidence coverage and acceptance policy are unchanged.
    policy_hash = hashlib.sha256(Path(policy.__file__).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    material = {"engine": ai.ENGINE_VERSION, "policy": policy_hash,
                "rules": ai.load_rules().model_dump(), "model": ai.model_name(),
                "enabled": ai.enabled(),
                "pages": get_env("PCT_AI_MAX_PAGES", default="5"),
                "dns": get_env("PCT_EMAIL_DNS_CHECK", default="true")}
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def load_handoff(path, input_file, rows):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("version") != 1 or data.get("input_sha256") != file_hash(input_file):
        raise ValueError("Resume handoff does not match the original input file")
    if data.get("total") != len(rows) or data.get("policy_fingerprint") != policy_fingerprint():
        raise ValueError("Resume handoff has different contact rules or row count")
    results = data.get("results")
    if not isinstance(results, list):
        raise ValueError("Resume handoff has no saved results")
    seen = set()
    mapping = {"patent_id": "id", "title": "title", "appl_no": "appl_no",
               "applicant": "applicant", "researcher": "researcher", "priority_date": "priority_date"}
    for result in results:
        index = result.get("row")
        if type(index) is not int or index < 1 or index > len(rows) or index in seen:
            raise ValueError("Resume handoff has invalid or duplicate row numbers")
        if result.get("status") not in {"found", "not_found", "error"}:
            raise ValueError("Resume handoff contains an unfinished result")
        if any(result.get(key, "") != rows[index - 1].get(source, "") for key, source in mapping.items()):
            raise ValueError(f"Resume handoff source mismatch at row {index}")
        if not all(isinstance(result.get(key, []), list) for key in ("emails", "phones")):
            raise ValueError("Resume handoff has malformed contact fields")
        seen.add(index)
    return sorted(results, key=lambda result: result["row"])
