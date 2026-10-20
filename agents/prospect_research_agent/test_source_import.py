"""Source batches tested with synthetic permissions and offline HTTP only."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from shared.prospect_store import ProspectStore

from . import source_api
from .source_formats import CollectionRecipe, extract_collection
from .source_import import ImportRequest, SourceImports, _same_month
from .test_directory_sources import TERMS_TEXT, permitted_policy
from .test_tools import response
from .tools import SourceError, SourceTools


URL = "https://directory.example/lawyers"
JSON_RECIPE = CollectionRecipe(format="json", records_path="data.people",
    field_paths={"name": "full_name", "email": "email", "role": "title", "firm": "company.name"},
    next_path="paging.next", query_keys=["page", "limit"])
HTML_RECIPE = CollectionRecipe(record_selector="article.lawyer",
    field_selectors={"name": "h2", "email": "a.email", "role": ".role", "website": "a.website"},
    next_selector="a.more")


def feed(people, next_url=None):
    return json.dumps({"data": {"people": people}, "paging": {"next": next_url}}).encode()


class FormatTests(unittest.TestCase):
    def page(self):
        return {"url": URL, "retrieved_at": "2026-10-20T10:00:00+00:00"}

    def test_two_different_html_layouts_use_their_own_recipes(self):
        first = "<article class='lawyer'><h2>Jane Example</h2><span class='role'>Partner</span><a class='email' href='mailto:jane@firm.example'>Email</a></article>"
        second = "<section id='people'><div class='person'><b class='name'>John Example</b><span class='address'>john@other.example</span></div></section>"
        data = extract_collection(first, self.page(), HTML_RECIPE)
        other = extract_collection(second, self.page(), CollectionRecipe(record_selector="#people .person",
            field_selectors={"name": ".name", "email": ".address"}))
        self.assertEqual(data["records"][0]["email"], "jane@firm.example")
        self.assertEqual(other["records"][0]["email"], "john@other.example")
        self.assertFalse(other["records"][0]["outreach_eligible"])

    def test_fields_never_cross_card_boundaries_or_capture_footer_email(self):
        html = "<article class='lawyer'><h2>Jane Example</h2></article><article class='lawyer'><h2>John Example</h2><a class='email'>john@firm.example</a></article><footer><a class='email'>help@directory.example</a></footer>"
        data = extract_collection(html, self.page(), HTML_RECIPE)
        self.assertNotIn("email", data["records"][0])
        self.assertEqual(data["records"][1]["email"], "john@firm.example")
        self.assertNotIn("help@directory.example", str(data["records"]))

    def test_ambiguous_email_and_next_links_stop_or_withhold(self):
        html = "<article class='lawyer'><h2>Jane Example</h2><a class='email'>a@firm.example b@firm.example</a></article>"
        self.assertNotIn("email", extract_collection(html, self.page(), HTML_RECIPE)["records"][0])
        with self.assertRaisesRegex(ValueError, "multiple next"):
            extract_collection(html + "<a class='more' href='/lawyers/2'>Next</a><a class='more' href='/lawyers/3'>Next</a>", self.page(), HTML_RECIPE)

    def test_layout_change_never_silently_looks_like_exhaustion(self):
        with self.assertRaisesRegex(ValueError, "layout_changed"):
            extract_collection("<div>New design</div>", self.page(), HTML_RECIPE)
        with self.assertRaisesRegex(ValueError, "record array"):
            extract_collection('{"new_records": []}', self.page(), JSON_RECIPE)
        with self.assertRaisesRegex(ValueError, "next-page field is missing"):
            extract_collection('{"data":{"people":[]}}', self.page(), JSON_RECIPE)

    def test_json_field_mapping_is_explicit_and_does_not_export_unrelated_payload(self):
        body = feed([{"full_name": "Jane Example", "email": "jane@firm.example", "private_notes": "ignore", "company": {"name": "Example Law"}}])
        data = extract_collection(body, self.page(), JSON_RECIPE)
        row = data["records"][0]
        self.assertEqual(row["firm"], "Example Law")
        self.assertEqual(row["evidence_path"], "data.people[0]")
        self.assertNotIn("private_notes", str(data))

    def test_large_pages_and_executable_recipes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "100 records"):
            extract_collection(feed([{}] * 101), self.page(), JSON_RECIPE)
        for kwargs in ({"record_selector": "script:has(*)"}, {"record_selector": ".card", "field_selectors": {"password": ".x"}},
                       {"format": "json", "field_paths": {"name": "name"}, "query_keys": ["api_key"]},
                       {"format": "json", "field_paths": {"name": "x[0]"}},
                       {"auth_env": "OPENAI_API_KEY"}):
            with self.assertRaises(ValidationError):
                CollectionRecipe(**kwargs)

    def test_input_rejects_credentials_internal_urls_and_secrets_in_queries(self):
        for url in ("http://127.0.0.1/", "http://localhost/", "https://user:password@public.example/", "https://public.example/?api_key=private", "https://public.example/?token=private"):
            with self.assertRaises((ValueError, RuntimeError)):
                ImportRequest(url=url)
        self.assertEqual(ImportRequest(url=URL).url, URL)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls, self.headers = [], []
        self.policy = permitted_policy(profile_path_prefixes=["/lawyers", "/lawyer"], collection=JSON_RECIPE)
        self.documents = {URL: feed([{"full_name": "Jane Example", "email": "jane@firm.example"}])}
        self.content_type = "application/json"
        self.status = 200
        def factory(profile, budget):
            tools = SourceTools(profile, budget)
            tools.directory_policy = self.policy
            tools._resolve_public_ips = lambda host: ["8.8.8.8"]
            def transport(url, address, headers, maximum):
                self.calls.append(url)
                self.headers.append((url, dict(headers)))
                if url.endswith("robots.txt"):
                    return response(url, status=404)
                if url.endswith("/terms"):
                    return response(url, body=TERMS_TEXT.encode())
                return response(url, status=self.status, body=self.documents[url], **{"content-type": self.content_type})
            tools._transport = transport
            return tools
        self.service = SourceImports(Path(self.temp.name) / "imports", factory)
        pacing = patch.object(self.service.store, "reserve_source_request", return_value=0)
        self.pacer = pacing.start()
        self.addCleanup(pacing.stop)
        self.addCleanup(lambda: self.service.executor.shutdown(wait=True))
        sleeper = patch("agents.prospect_research_agent.tools.time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def run_job(self, **kwargs):
        state = self.service.start({"url": URL, **kwargs})
        self.service.future.result(timeout=5)
        return self.service.get(state["job_id"])

    def test_json_pagination_bulk_deduplicates_and_is_not_qualified_inventory(self):
        self.documents[URL] = feed([{"full_name": "Jane Example", "email": "jane@firm.example"}], "/lawyers?page=2")
        self.documents[URL + "?page=2"] = feed([{"full_name": "Jane Example", "email": "jane@firm.example"}, {"full_name": "John Example", "email": "john@firm.example"}])
        job = self.run_job()
        self.assertEqual(job["status"], "complete", job)
        self.assertEqual(len(job["records"]), 2)
        self.assertEqual(job["pages_read"], 2)
        self.assertEqual(job["budget"]["counts"]["queries"], 0)
        self.assertEqual(job["budget"]["counts"]["verifications"], 0)
        self.assertEqual(job["budget"]["counts"]["llm_calls"], 0)
        self.assertTrue(all(row["verification_status"] == "not_checked" and not row["outreach_eligible"] for row in job["records"]))
        self.assertEqual(self.service.store.records("any"), [])

    def test_monthly_reuse_preserves_original_retrieval_and_checks_current_access(self):
        first = self.run_job()
        self.calls.clear()
        second = self.run_job()
        self.assertEqual(second["status"], "cached")
        self.assertNotIn(URL, self.calls)
        self.assertTrue(any(url.endswith("/terms") for url in self.calls))
        self.assertEqual(first["records"][0]["retrieved_at"], second["records"][0]["retrieved_at"])
        self.service.store.hold_source("directory.example", "Operator hold")
        self.calls.clear()
        self.assertEqual(self.run_job()["status"], "held")
        self.assertEqual(self.calls, [])

    def test_fifty_record_batch_buffers_the_rest_and_resumes_without_download(self):
        self.documents[URL] = feed([{"full_name": f"Lawyer {index}", "email": f"person{index}@firm.example"} for index in range(60)])
        first = self.run_job()
        self.assertEqual(first["status"], "partial")
        self.assertEqual(len(first["records"]), 50)
        self.calls.clear()
        second = self.run_job()
        self.assertEqual(second["status"], "complete", second)
        self.assertEqual(len(second["records"]), 60)
        self.assertNotIn(URL, self.calls)

    def test_exactly_fifty_without_more_pages_is_complete(self):
        self.documents[URL] = feed([{"email": f"person{index}@firm.example"} for index in range(50)])
        self.assertEqual(self.run_job()["status"], "complete")

    def test_same_site_can_route_listing_and_profile_pages_to_different_layouts(self):
        listing = CollectionRecipe(profile_link_selector="a.profile", next_selector="a.more")
        profile = CollectionRecipe(record_selector="section.person", field_selectors={"name": "h1", "email": "a.contact"})
        self.policy = permitted_policy(profile_path_prefixes=["/lawyers", "/lawyer"], collection_routes=[
            {"path_prefix": "/lawyers", "reader": listing}, {"path_prefix": "/lawyer", "reader": profile}])
        self.content_type = "text/html"
        self.documents[URL] = b"<a class='profile' href='/lawyer/jane'>Jane Example</a>"
        self.documents["https://directory.example/lawyer/jane"] = b"<section class='person'><h1>Jane Example</h1><a class='contact' href='mailto:jane@firm.example'>Email</a></section>"
        result = self.run_job()
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual(result["records"][0]["email"], "jane@firm.example")
        self.assertEqual(result["pages_read"], 2)

    def test_next_month_rechecks_data_and_marks_unchanged_records(self):
        first = self.run_job()
        saved = self.service._read(first["job_id"])
        saved["completed_at"] = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        self.service._write(saved)
        self.calls.clear()
        refreshed = self.run_job()
        self.assertEqual(refreshed["status"], "complete")
        self.assertIn(URL, self.calls)
        self.assertEqual(refreshed["records"][0]["change"], "unchanged")

    def test_oversized_or_secret_numeric_pagination_cannot_trigger_an_api_request(self):
        for query in ("limit=10000", "page=private-value", "page=2&page=3"):
            with self.assertRaises(SourceError):
                self.service.start({"url": URL + "?" + query})
        self.assertEqual(self.calls, [])

    def test_refresh_detects_new_and_changed_contacts(self):
        self.run_job()
        self.documents[URL] = feed([{"full_name": "Jane Example", "email": "jane@firm.example", "title": "Partner"}, {"email": "new@firm.example"}])
        refreshed = self.run_job(refresh=True)
        self.assertEqual([row["change"] for row in refreshed["records"]], ["changed", "new"])

    def test_source_page_cap_keeps_next_url_for_an_explicit_later_batch(self):
        for index in range(5):
            self.documents[URL + (f"?page={index}" if index else "")] = feed([{"email": f"p{index}@firm.example"}], f"/lawyers?page={index + 1}" if index < 4 else None)
        first = self.run_job()
        self.assertEqual(first["status"], "partial", first)
        self.assertEqual(first["pages_read"], 3)
        second = self.run_job()
        self.assertEqual(second["status"], "complete", second)
        self.assertEqual(len(second["records"]), 5)

    def test_restricted_source_is_held_without_network_or_records(self):
        self.policy = permitted_policy(state="restricted")
        result = self.run_job()
        self.assertEqual(result["status"], "held")
        self.assertEqual(result["records"], [])
        self.assertEqual(self.calls, [])

    def test_navigation_cannot_escape_source_paths_hosts_or_add_credentials(self):
        for next_url in ("https://other.example/lawyers", "http://directory.example/lawyers?page=2", "http://127.0.0.1/", "/private", "/lawyers?api_key=private", URL):
            self.documents[URL] = feed([{"email": "jane@firm.example"}], next_url)
            self.calls.clear()
            result = self.run_job(refresh=True)
            self.assertEqual(result["status"], "held", next_url)
            self.assertLessEqual(self.calls.count(next_url), 1 if next_url == URL else 0)

    def test_http_denial_persists_hold_across_jobs(self):
        self.status = 403
        self.assertEqual(self.run_job()["status"], "held")
        self.calls.clear()
        self.assertEqual(self.run_job(refresh=True)["status"], "held")
        self.assertEqual(self.calls, [])

    def test_authentication_only_uses_dedicated_env_on_exact_https_feed_host(self):
        recipe = JSON_RECIPE.model_copy(update={"auth_env": "PROSPECT_RESEARCH_AGENT_SOURCE_DIRECTORY_KEY", "auth_header": "X-API-Key"})
        self.policy = permitted_policy(profile_path_prefixes=["/lawyers"], collection=recipe)
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SOURCE_DIRECTORY_KEY": "fixture-private-value"}):
            job = self.run_job()
        self.assertEqual(job["status"], "complete")
        for url, headers in self.headers:
            self.assertEqual(headers.get("X-API-Key"), "fixture-private-value" if url == URL else None)
        self.assertNotIn("fixture-private-value", json.dumps(job))

    def test_plain_website_test_is_only_one_page_with_unverified_contacts(self):
        self.policy = permitted_policy(host="other.example")
        self.content_type = "text/html"
        self.documents[URL] = b"<title>Example Law</title><h1>Example Law</h1>Law firm. Contact: info@directory.example"
        result = self.run_job()
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual(result["coverage"], "page_only")
        self.assertIn("Whole-site coverage has not been established", result["message"])
        self.assertEqual(result["records"][0]["email"], "info@directory.example")

    def test_api_routes_enforce_auth_role_origin_and_body_limits(self):
        app = FastAPI()
        async def authorize(request, write=False):
            if request.headers.get("x-login") != "yes":
                raise HTTPException(401, "Login required")
            if write and request.headers.get("origin") != "https://os.example":
                raise HTTPException(403, "Origin required")
            return {"role": request.headers.get("x-role", "operator")}
        with patch.object(source_api, "SourceImports", return_value=self.service):
            source_api.register_routes(app, authorize, self.service.directory)
            with TestClient(app) as client:
                self.assertEqual(client.get(source_api.BASE).status_code, 401)
                self.assertEqual(client.get(source_api.BASE, headers={"x-login": "yes", "x-role": "viewer"}).status_code, 403)
                headers = {"x-login": "yes", "origin": "https://os.example"}
                self.assertEqual(client.post(source_api.BASE, json={"url": URL}, headers={"x-login": "yes"}).status_code, 403)
                self.assertEqual(client.post(source_api.BASE, json={"url": URL, "enable_verification": True}, headers=headers).status_code, 422)
                self.assertEqual(client.post(source_api.BASE, content="x" * 4001, headers=headers).status_code, 413)
                result = client.post(source_api.BASE, json={"url": URL}, headers=headers)
                self.assertEqual(result.status_code, 200)
                self.service.future.result(timeout=5)
                saved = client.get(source_api.BASE, headers=headers)
                self.assertEqual(saved.headers["cache-control"], "private, no-store")
                self.assertEqual(saved.json()["status"], "complete")
                self.assertNotIn("queue", saved.json())
                self.assertEqual(client.get(source_api.BASE + "/not-a-job", headers=headers).status_code, 404)

    def test_month_boundary_and_future_dates_do_not_pin_source_forever(self):
        self.assertFalse(_same_month((datetime.now(timezone.utc) + timedelta(days=2)).isoformat()))
        self.assertFalse(_same_month((datetime.now(timezone.utc) - timedelta(days=35)).isoformat()))
        self.assertFalse(_same_month("broken"))

    def test_pacing_slots_survive_workers_and_cannot_be_shortened_by_parallel_requests(self):
        directory = Path(self.temp.name) / "pacing"
        stores = [ProspectStore(directory) for _ in range(10)]
        with patch("shared.prospect_store.time.time", return_value=1000):
            with ThreadPoolExecutor(max_workers=10) as pool:
                waits = list(pool.map(lambda store: store.reserve_source_request("directory.example", 2, 100), stores))
            self.assertEqual(sorted(waits), list(range(0, 20, 2)))
            self.assertIsNone(stores[0].reserve_source_request("directory.example", 2, 5))
            self.assertEqual(ProspectStore(directory).reserve_source_request("directory.example", 2, 100), 20)

    def test_waiting_for_an_earlier_batch_preserves_progress_without_persisting_a_denial(self):
        self.pacer.return_value = None
        result = self.run_job()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.service.store.source_hold("directory.example"))

    def test_interrupted_worker_is_resumable_after_service_restart(self):
        job = self.run_job()
        state = self.service._read(job["job_id"])
        state.update(status="running", completed_at=None)
        self.service._write(state)
        restarted = SourceImports(self.service.directory)
        self.addCleanup(lambda: restarted.executor.shutdown(wait=True))
        self.assertEqual(restarted.get(job["job_id"])["status"], "partial")
        self.assertEqual(restarted.get(job["job_id"])["records"], job["records"])


if __name__ == "__main__":
    unittest.main()
