import json
from pathlib import Path

import fitz
import pytest

from agents.pct_agent import ai_verifier as ai
from agents.pct_agent import pdf_extractor


def field(value="johnl@example.com", **changes):
    data = dict(kind="email", value=value, entity="John Lee", role="agent", page=1,
                evidence="Email: " + value, legible=True, block_id="page1-agent1",
                section="Agent / representative", entity_type="law_firm")
    data.update(changes)
    return ai.ContactField(**data)


def extraction(*fields, uncertainties=None):
    return ai.VisualExtraction(fields=list(fields), reviewed_pages=[1], uncertainties=uncertainties or [])


def pdf(tmp_path):
    path = tmp_path / "filing.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 60), "Agent: John Lee\nEmail: johnl@example.com\nTelephone: +1 212 555 0181", fontsize=16)
        doc.save(path)
    return path


def test_image_read_can_correct_plausible_but_wrong_ocr(tmp_path, monkeypatch):
    monkeypatch.setenv("PCT_AI_EVIDENCE_DIR", str(tmp_path / "evidence"))
    monkeypatch.setattr(ai, "_request", lambda pages, rules, context: extraction(field()))
    result = ai.verify_contacts(pdf(tmp_path), {"emails": ["john1@example.com"]})
    assert result["emails"] == ["johnl@example.com"]
    record = json.loads(Path(result["evidence_file"]).read_text())
    assert record["ocr_candidates"]["emails"] == ["john1@example.com"]
    assert Path(result["evidence_file"]).with_name("source.pdf").exists()


@pytest.mark.parametrize("candidate", [field(legible=False), field(page=5), field(evidence="Email unreadable"), field(entity="")])
def test_unsupported_fields_are_not_exported(candidate):
    result = ai.select_contacts(extraction(candidate), ai.load_rules(), [1])
    assert result["ai_status"] == "needs_review"
    assert result["emails"] == []
    assert result["status"] != "found"


def test_office_contacts_and_fax_are_excluded():
    result = ai.select_contacts(extraction(field("pct@wipo.int", role="patent_office"),
                                          field("+1 212 555 0100", kind="fax")), ai.load_rules(), [1])
    assert result["ai_status"] == "no_wanted_contacts"
    assert result["phones"] == []


def test_role_rules_apply_even_if_model_ignores_them():
    rules = ai.load_rules().model_copy(update={"include_roles": ["applicant"]})
    assert ai.select_contacts(extraction(field()), rules, [1])["emails"] == []


def test_different_owners_are_held_for_review():
    result = ai.select_contacts(extraction(field(), field("other@example.com", entity="Other Person")), ai.load_rules(), [1])
    assert result["ai_status"] == "needs_review"


def test_ai_failure_never_falls_back_to_unverified_ocr(tmp_path, monkeypatch):
    monkeypatch.setenv("PCT_AI_EVIDENCE_DIR", str(tmp_path / "evidence"))
    def fail(*args):
        raise RuntimeError("openai_http_429")
    monkeypatch.setattr(ai, "_request", fail)
    result = ai.verify_contacts(pdf(tmp_path), {"emails": ["john1@example.com"]})
    assert result["status"] == "error" and result["emails"] == []
    assert Path(result["evidence_file"]).exists()


def test_changed_rules_invalidate_verified_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("PCT_AI_EVIDENCE_DIR", str(tmp_path / "evidence"))
    calls = []
    def request(*args):
        calls.append(1)
        return extraction(field())
    monkeypatch.setattr(ai, "_request", request)
    source = pdf(tmp_path)
    ai.verify_contacts(source, {})
    ai.verify_contacts(source, {})
    assert len(calls) == 1
    rules = ai.load_rules().model_dump()
    rules["instructions"].append("Only direct contact addresses")
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps(rules))
    monkeypatch.setenv("PCT_AI_RULES_FILE", str(rules_path))
    ai.verify_contacts(source, {})
    assert len(calls) == 2


def test_extractor_routes_through_ai_and_passes_context(monkeypatch):
    monkeypatch.setenv("PCT_AI_VERIFY_ENABLED", "true")
    monkeypatch.setattr(pdf_extractor, "_extract_ocr_contacts", lambda *args: {"emails": ["bad@example.com"]})
    def verify(path, candidates, step, context):
        assert context == {"id": "WO1"}
        return {"status": "not_found", "emails": [], "ai_status": "needs_review"}
    monkeypatch.setattr(ai, "verify_contacts", verify)
    assert pdf_extractor.extract_contacts_from_pdf("unused.pdf", context={"id": "WO1"})["emails"] == []


def test_applicant_cache_cannot_bypass_document_verification(monkeypatch):
    from agents.pct_agent.pipeline import ContactCache
    monkeypatch.setenv("PCT_AI_VERIFY_ENABLED", "true")
    cache = ContactCache()
    cache.put("Same Applicant", {"status": "found", "emails": ["old@example.com"]})
    assert cache.get("Same Applicant") is None


def test_legacy_progress_does_not_skip_ai_verification(tmp_path, monkeypatch):
    from agents.pct_agent.pipeline import ProgressFile
    monkeypatch.setenv("PCT_AI_VERIFY_ENABLED", "true")
    path = tmp_path / "progress.jsonl"
    path.write_text(json.dumps({"patent_id": "WO1", "status": "found"}) + "\n")
    assert ProgressFile.load_completed(path) == set()


def test_report_matches_aneeq_columns_exactly(tmp_path, monkeypatch):
    import openpyxl
    from agents.pct_agent import agent
    monkeypatch.setattr(agent, "PCT_OUTPUT_DIR", tmp_path)
    expected = ["Publication No", "Title", "Application No.", "Applicant", "Url", "Cat",
                "Phone No.", "Email", "Agent Name", "Country", "Researcher", "Priorty Date"]
    for kind in ("worked", "not_found"):
        path = agent.generate_work_report([{"row": 1, "patent_id": "WO1", "ai_status": "needs_review",
                                           "reason": "Unclear l/1", "evidence_file": "source.pdf",
                                           "researcher": "Aneeq", "priority_date": "05 August to 10 August 2026"}], kind=kind)
        wb = openpyxl.load_workbook(path)
        assert wb.active.max_column == 12
        assert [c.value for c in wb.active[1]] == expected
        assert wb.active.cell(2, 11).value == "Aneeq"
        assert wb.active.cell(2, 12).value == "05 August to 10 August 2026"
        assert wb.active.cell(2, 8).value is None


def test_quota_failure_is_reported_before_a_scrape_starts(monkeypatch):
    from agents.pct_agent import agent
    def unavailable(**kwargs):
        assert kwargs["check_api"] is True
        raise ValueError("openai_http_429_credit_balance_exhausted")
    monkeypatch.setattr(agent, "validate_configuration", unavailable)
    result = agent.run_agent({"mode": "wipo_download"})
    assert result["status"] == "failure"
    assert "credit_balance_exhausted" in result["error"]


def test_machine_error_does_not_expose_raw_response():
    class Response:
        status_code = 429
        def json(self):
            return {"error": {"code": "credit_balance_exhausted", "message": "private request content"}}
    assert ai._api_error(Response()) == "openai_http_429_credit_balance_exhausted"
