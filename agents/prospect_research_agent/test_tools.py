"""Isolated source tests: no provider account or live website is contacted."""

import io
import json
import os
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from .tools import HTTPResult, SourceError, SourceTools, _PinnedConnection, validate_public_url


class _Budget:
    def __init__(self, **limits):
        self.counts = Counter()
        self.limits = limits
        self.cancelled = False

    def check(self):
        if self.cancelled:
            raise RuntimeError("RunCancelled")

    def remaining_seconds(self):
        return 90

    def consume(self, kind, amount=1):
        self.check()
        if self.counts[kind] + amount > self.limits.get(kind, 999):
            raise RuntimeError("BudgetExceeded")
        self.counts[kind] += amount


def request(**overrides):
    fields = dict(mode="live", countries=["India", "United States"], query_terms=["law firm"],
                  max_queries=2, max_candidates=5, max_pages_per_firm=3,
                  request_timeout=2, enable_verification=False, exclude_domains=[])
    fields.update(overrides)
    return SimpleNamespace(**fields)


def response(url, status=200, body=b"", content_type="text/html", **headers):
    return HTTPResult(status, {"content-type": content_type, **headers}, body, url)


class SourceToolTests(unittest.TestCase):
    def test_discovery_preserves_configured_query_across_extraction_strategies(self):
        source = SourceTools(request(countries=[], max_queries=1), _Budget())
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "test-only"}), patch.object(source, "_provider_json", return_value=(200, {"organic_results": []})) as provider:
            source.discover("focused")
        query = parse_qs(urlsplit(provider.call_args.args[1]).query)["q"]
        self.assertEqual(query, ["law firm"])

    def test_discovery_rejects_results_for_a_different_query(self):
        source = SourceTools(request(countries=[], max_queries=1), _Budget())
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "test-only"}), patch.object(source, "_provider_json", return_value=(200, {"search_parameters": {"q": "unrelated"}, "organic_results": []})):
            with self.assertRaisesRegex(SourceError, "query_mismatch"):
                source.discover()

    def setUp(self):
        self.budget = _Budget()
        self.tools = SourceTools(request(), self.budget)
        self.address_patch = patch.object(self.tools, "_resolve_public_ips", return_value=["8.8.8.8"])
        self.address_patch.start()
        self.addCleanup(self.address_patch.stop)

    def test_rejects_private_credentials_queries_and_obfuscated_destinations(self):
        blocked = [
            "file:///etc/passwd", "http://localhost/", "http://service.internal/",
            "http://127.0.0.1/", "http://10.0.0.8/", "http://169.254.169.254/",
            "http://[::1]/", "http://[::ffff:127.0.0.1]/", "https://user:password@firm.example/",
            "https://firm.example/?api_key=credential", "https://firm.example/?",
            "https://firm.example:8443/", "https://firm.example/%0d%0aHeader:bad",
            "https://firm.example\\@127.0.0.1/", "http://2130706433/",
            "http://224.0.0.1/", "http://[ff02::1]/", "http://[2002:7f00:1::]/",
        ]
        for url in blocked:
            with self.subTest(url=url), self.assertRaises(SourceError):
                validate_public_url(url)

    def test_dns_rejects_mixed_public_and_private_answers(self):
        from . import tools as module
        with patch("dns.resolver.Resolver") as resolver:
            resolver.return_value.resolve.side_effect = [["8.8.8.8"], ["::1"]]
            with self.assertRaisesRegex(SourceError, "unsafe_dns"):
                module.SourceTools(request(), self.budget)._resolve_public_ips("firm.example")
            lifetime = resolver.return_value.resolve.call_args.kwargs["lifetime"]
            self.assertGreater(lifetime, 0)
            self.assertLessEqual(lifetime, 2)

    def test_socket_connects_to_validated_ip_without_second_dns_lookup(self):
        with patch("socket.socket") as socket_factory, patch("socket.getaddrinfo") as getaddrinfo, patch("ssl.create_default_context") as tls:
            raw_socket = socket_factory.return_value
            connection = _PinnedConnection("firm.example", "8.8.8.8", 443, 1, True)
            connection.connect()
            raw_socket.connect.assert_called_once_with(("8.8.8.8", 443))
            tls.return_value.wrap_socket.assert_called_once_with(raw_socket, server_hostname="firm.example")
            getaddrinfo.assert_not_called()

    def test_outside_host_redirect_is_blocked_before_connection(self):
        def fetch(url, address, headers, max_bytes):
            if url.endswith("robots.txt"):
                return response(url, status=404)
            return response(url, status=302, location="http://127.0.0.1/admin")
        with patch.object(self.tools, "_transport", side_effect=fetch) as transport:
            pages = self.tools.read_firm("https://firm.example/")
        self.assertEqual(transport.call_count, 2)
        self.assertIn("unsafe_url", pages[0]["error"])

    def test_same_host_redirect_rechecks_dns_for_rebinding(self):
        self.address_patch.stop()
        calls = []
        def fetch(url, address, headers, max_bytes):
            calls.append(url)
            if url.endswith("robots.txt"):
                return response(url, status=404)
            return response(url, status=302, location="/contact")
        with patch.object(self.tools, "_resolve_public_ips", side_effect=[["8.8.8.8"], ["8.8.8.8"], SourceError("unsafe_dns: private destination")]), patch.object(self.tools, "_transport", side_effect=fetch):
            pages = self.tools.read_firm("https://firm.example/")
        self.assertEqual(len(calls), 2)
        self.assertIn("unsafe_dns", pages[0]["error"])

    def test_www_redirect_uses_new_dns_policy_and_keeps_followup_links(self):
        calls = []
        def fetch(url, address, headers, max_bytes):
            calls.append(url)
            if url.endswith("robots.txt"): return response(url, status=404)
            if url == "https://firm.example/":
                return response(url, status=301, location="https://www.firm.example/")
            return response(url, body=b"Law firm <a href='/contact'>Contact</a>")
        with patch.object(self.tools, "_transport", side_effect=fetch), patch.object(self.tools, "_resolve_public_ips", return_value=["8.8.8.8"]) as dns:
            pages = self.tools.read_firm("https://firm.example/")
        self.assertEqual(pages[0]["url"], "https://www.firm.example/")
        self.assertIn("https://www.firm.example/robots.txt", calls)
        self.assertIn("https://www.firm.example/contact", calls)
        self.assertIn(unittest.mock.call("www.firm.example"), dns.call_args_list)

    def test_www_redirect_respects_destination_robots_and_rebinding(self):
        def fetch(url, address, headers, max_bytes):
            if url == "https://firm.example/robots.txt": return response(url, status=404)
            if url == "https://www.firm.example/robots.txt": return response(url, body=b"User-agent: *\nDisallow: /\n")
            return response(url, status=301, location="https://www.firm.example/")
        with patch.object(self.tools, "_transport", side_effect=fetch) as transport:
            pages = self.tools.read_firm("https://firm.example/")
        self.assertIn("robots_disallowed", pages[0]["error"])
        self.assertEqual(transport.call_count, 3)

    def test_other_subdomain_is_not_a_www_alias(self):
        for target in ("https://api.firm.example/", "https://firm.example.evil.example/"):
            tools = SourceTools(request(), _Budget())
            with patch.object(tools, "_resolve_public_ips", return_value=["8.8.8.8"]), patch.object(tools, "_transport", side_effect=lambda url,*args: response(url,status=404) if url.endswith('robots.txt') else response(url,status=302,location=target)) as transport:
                pages = tools.read_firm("https://firm.example/")
            self.assertIn("blocked_redirect", pages[0]["error"])
            self.assertEqual(transport.call_count, 2)

    def test_missing_country_after_team_page_prefers_contact_over_another_bio(self):
        self.tools.incremental_read = True
        def fetch(url, *args):
            if url.endswith("robots.txt"): return response(url, status=404)
            return response(url, body=b"Team <a href='/attorneys/jane'>Jane</a><a href='/contact'>Contact</a>")
        with patch.object(self.tools, "_transport", side_effect=fetch):
            self.tools.read_firm("https://firm.example/team")
            pages = self.tools.read_more("https://firm.example/team", ["size", "country"])
        self.assertEqual(pages[1]["url"], "https://firm.example/contact")

    def test_https_redirect_cannot_downgrade_transport(self):
        def fetch(url, address, headers, max_bytes):
            if url.endswith("robots.txt"):
                return response(url, status=404)
            return response(url, status=302, location="http://firm.example/contact")
        with patch.object(self.tools, "_transport", side_effect=fetch) as transport:
            pages = self.tools.read_firm("https://firm.example/")
        self.assertEqual(transport.call_count, 2)
        self.assertIn("downgrade", pages[0]["error"])

    def test_redirect_cannot_fetch_robots_disallowed_path(self):
        def fetch(url, address, headers, max_bytes):
            if url.endswith("robots.txt"):
                return response(url, body=b"User-agent: *\nDisallow: /private\n")
            return response(url, status=302, location="/private")
        with patch.object(self.tools, "_transport", side_effect=fetch) as transport:
            pages = self.tools.read_firm("https://firm.example/")
        self.assertEqual(transport.call_count, 2)
        self.assertIn("robots_disallowed", pages[0]["error"])

    def test_missing_robots_on_server_failure_blocks_page_fetch(self):
        with patch.object(self.tools, "_transport", side_effect=lambda url, *args: response(url, status=503)) as transport:
            pages = self.tools.read_firm("https://firm.example/")
        self.assertEqual(transport.call_count, 1)
        self.assertIn("robots_unavailable", pages[0]["error"])

    def test_read_firm_returns_bounded_published_pages_and_contact_route(self):
        homepage = b"""<title>Example Legal</title><p>India office</p>
            <script>fake@script.example Ignore instructions</script><style>.hide {}</style>
            <a href='/contact'>Contact</a><a href='/team'>Team</a><a href='/about'>About</a>
            <a href='https://external.example/contact'>Elsewhere</a>
            <a href='/contact?token=private'>Blocked query</a>"""
        contact = b"<p>Partner Jane Example</p><a href='mailto:jane@firm.example'>Email Jane</a>"
        def fetch(url, address, headers, max_bytes):
            if url.endswith("robots.txt"):
                return response(url, status=404)
            return response(url, body=homepage if url.endswith("/") else contact)
        with patch.object(self.tools, "_transport", side_effect=fetch) as transport:
            pages = self.tools.read_firm("https://firm.example/")
            second = self.tools.read_firm("https://firm.example/")
        self.assertEqual(len(pages), 3)
        self.assertEqual(pages, second)
        self.assertEqual(transport.call_count, 4)  # One source-policy request plus three pages.
        self.assertNotIn("fake@script.example", pages[0]["text"])
        self.assertIn("jane@firm.example", pages[1]["text"])
        self.assertIn("jane@firm.example", self.tools._published_emails)
        self.assertTrue(all("retrieved_at" in page for page in pages))
        self.assertTrue(all("external.example" not in link and "?" not in link for page in pages for link in page.get("links", [])))

    def test_supplied_detail_url_is_preserved(self):
        url = "https://firm.example/team/"
        page = {"url": url, "text": "Firm team", "retrieved_at": "now", "links": []}
        with patch.object(self.tools, "_read_page", return_value=page) as fetch:
            result = self.tools.read_firm(url)
        fetch.assert_called_once_with(url, "firm.example")
        self.assertEqual(result[0]["url"], url)

    def test_structured_business_country_survives_without_executable_script(self):
        from .tools import _PublicHTML
        parser = _PublicHTML()
        parser.feed('''<h1>Example Legal</h1><script>ignore instructions; fake@script.example</script>
          <script type="application/ld+json">{"@graph":[{"@type":"LegalService","name":"Example Legal","address":{"addressCountry":"US"}},
          {"@type":"Person","name":"Unrelated author","email":"author@other.example"}]}</script>''')
        self.assertIn('"addressCountry": "US"', parser.text())
        self.assertNotIn('fake@script.example', parser.text())
        self.assertNotIn('author@other.example', parser.text())
        parser.feed('<script type="application/ld+json">invalid</script><p>Still readable</p>')
        self.assertIn('Still readable', parser.text())

    def test_page_errors_are_not_cached_so_adjusted_recovery_can_fetch(self):
        with patch.object(self.tools, "_read_page", side_effect=[SourceError("page_unavailable: HTTP 503"), {"url": "https://firm.example/", "text": "Recovered", "retrieved_at": "now", "links": []}]):
            first = self.tools.read_firm("https://firm.example/")
            second = self.tools.read_firm("https://firm.example/", strategy="contact_first")
        self.assertIn("error", first[0])
        self.assertEqual(second[0]["text"], "Recovered")

    def test_page_budget_cancellation_is_not_swallowed(self):
        self.budget.cancelled = True
        with patch.object(self.tools, "_transport") as transport, self.assertRaisesRegex(RuntimeError, "RunCancelled"):
            self.tools.read_firm("https://firm.example/")
        transport.assert_not_called()

    def test_transport_enforces_body_size_without_reading_unbounded_data(self):
        stream = io.BytesIO(b"x" * 100)
        fake_response = SimpleNamespace(status=200, getheaders=lambda: [], read=stream.read)
        connection = MagicMock()
        connection.getresponse.return_value = fake_response
        with patch("agents.prospect_research_agent.tools._PinnedConnection", return_value=connection):
            with self.assertRaisesRegex(SourceError, "source_too_large"):
                self.tools._transport("https://firm.example/", "8.8.8.8", {}, 20)
        connection.close.assert_called_once()
        self.assertEqual(stream.tell(), 21)

    def test_provider_transport_errors_never_include_key_or_private_url(self):
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "mock-sensitive-token"}), patch.object(self.tools, "_transport", side_effect=OSError("failed https://serpapi.com/?api_key=mock-sensitive-token")):
            with self.assertRaises(SourceError) as caught:
                self.tools.discover()
        self.assertNotIn("mock-sensitive-token", str(caught.exception))
        self.assertNotIn("https://", str(caught.exception))

    def test_provider_auth_error_body_is_not_returned(self):
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "mock-sensitive-token"}), patch.object(self.tools, "_transport", side_effect=lambda url, *args: response(url, status=401, body=b"mock-sensitive-token secret provider error")):
            with self.assertRaisesRegex(SourceError, "authentication_failed") as caught:
                self.tools.discover()
        self.assertNotIn("mock-sensitive-token", str(caught.exception))

    def test_provider_json_error_text_is_redacted(self):
        payload = {"error": "secret provider URL api_key=mock-sensitive-token"}
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "mock-sensitive-token"}), patch.object(self.tools, "_transport", side_effect=lambda url, *args: response(url, body=json.dumps(payload).encode())):
            with self.assertRaisesRegex(SourceError, "provider_error") as caught:
                self.tools.discover()
        self.assertNotIn("mock-sensitive-token", str(caught.exception))

    def test_discovery_query_limit_deduplication_exclusion_and_url_policy(self):
        payload = {"search_metadata": {"status": "Success"}, "organic_results": [
            {"link": "https://firm.example/team"}, {"link": "https://www.firm.example/contact"},
            {"link": "https://excluded.example/"}, {"link": "http://127.0.0.1/"},
            {"link": "https://www.linkedin.com/company/example"}, {"link": "https://lawzana.com/lawyers"},
            {"link": "https://firm.example/press.pdf"},
            {"link": "https://signed.example/contact?token=mock-sensitive-token"},
        ]}
        self.tools.request.exclude_domains = ["excluded.example"]
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "mock-sensitive-token"}), patch.object(self.tools, "_transport", side_effect=lambda url, *args: response(url, body=json.dumps(payload).encode(), content_type="application/json")) as transport:
            first = self.tools.discover()
            second = self.tools.discover(strategy="official")
        self.assertEqual(first, ["https://firm.example/team"])
        self.assertEqual(second, [])
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(self.budget.counts["queries"], 2)
        queries = [parse_qs(urlsplit(call.args[0]).query)["q"][0] for call in transport.call_args_list]
        self.assertTrue(any("India" in query for query in queries))
        self.assertTrue(any("United States" in query for query in queries))

    def test_shared_search_key_requires_explicit_opt_in(self):
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "mock-shared-token"}, clear=True), patch.object(self.tools, "_transport") as transport:
            with self.assertRaisesRegex(SourceError, "explicit opt-in"):
                self.tools.discover()
        transport.assert_not_called()

    def test_async_search_polls_archive_without_starting_another_query(self):
        self.tools.request.max_queries = 1
        pending = {"search_metadata": {"status": "Processing", "id": "a" * 24}}
        completed = {"search_metadata": {"status": "Success"}, "organic_results": [{"link": "https://firm.example/about"}]}
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "mock-token"}), patch.object(self.tools, "_provider_json", side_effect=[(200, pending), (200, completed)]) as provider, patch("agents.prospect_research_agent.tools.time.sleep"):
            self.assertEqual(self.tools.discover(), ["https://firm.example/about"])
        self.assertEqual(self.budget.counts['queries'], 1)
        self.assertIn('/searches/' + 'a' * 24, provider.call_args.args[1])

    def test_transient_search_failure_changes_strategy_and_reserves_retry(self):
        completed = {"search_metadata": {"status": "Success"}, "organic_results": [{"link": "https://firm.example/about"}]}
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_SERPAPI_API_KEY": "mock-token"}), patch.object(self.tools, "_provider_json", side_effect=[SourceError('serpapi_request_failed: HTTP 503'), (200, completed)]) as provider:
            self.assertEqual(self.tools.discover(), ['https://firm.example/about'])
        self.assertEqual(self.budget.counts['queries'], 2)
        self.assertNotIn('async', parse_qs(urlsplit(provider.call_args.args[1]).query))

    def test_fixture_mode_performs_no_network(self):
        fixture = SourceTools(request(mode="fixture"), self.budget)
        with patch.object(fixture, "_fetch") as fetch:
            self.assertEqual(fixture.discover(), [])
            self.assertEqual(fixture.read_firm("https://firm.example/"), [])
            self.assertEqual(fixture.verify_email("jane@firm.example")["status"], "published_unverified")
        fetch.assert_not_called()

    def test_langchain_wrappers_invoke_fixture_methods(self):
        fixture = SourceTools(request(mode="fixture"), self.budget)
        try:
            wrappers = fixture.get_langchain_tools()
        except SourceError as error:
            if "langchain_dependency_missing" in str(error):
                self.skipTest("LangChain dependency is not installed in this test interpreter")
            raise
        self.assertEqual(set(wrappers), {"discover", "read_firm", "verify_email", "read_more", "resolve_directory"})
        with patch.object(fixture, "_fetch") as fetch:
            self.assertEqual(wrappers["discover"].invoke({"strategy": "standard"}), [])
            self.assertEqual(wrappers["read_firm"].invoke({"url": "https://firm.example/"}), [])
            self.assertEqual(wrappers["verify_email"].invoke({"email": "jane@firm.example"})["status"], "published_unverified")
        fetch.assert_not_called()

    def test_verification_requires_a_published_email(self):
        self.tools.request.enable_verification = True
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY": "mock-sensitive-token"}), patch.object(self.tools, "_fetch") as fetch:
            result = self.tools.verify_email("unpublished@firm.example")
        self.assertIn("verification_blocked", result["error"])
        fetch.assert_not_called()

    def test_pending_verification_has_bounded_polling_and_no_secret_url(self):
        self.tools.request.enable_verification = True
        self.tools._published_emails.add("jane@firm.example")
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY": "mock-sensitive-token"}), patch.object(self.tools, "_fetch", side_effect=lambda url, **kwargs: response(url, status=202)) as fetch, patch("time.sleep"):
            result = self.tools.verify_email("jane@firm.example")
        self.assertEqual(result, {"status": "pending", "verified_at": None, "provider": "hunter"})
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(self.budget.counts["verifications"], 3)
        self.assertTrue(all("mock-sensitive-token" not in call.args[0] for call in fetch.call_args_list))
        self.assertEqual(fetch.call_args.kwargs["headers"]["X-API-KEY"], "mock-sensitive-token")

    def test_provider_verification_date_and_catch_all_are_preserved(self):
        self.tools.request.enable_verification = True
        self.tools._published_emails.add("jane@firm.example")
        payload = {"data": {"status": "valid", "accept_all": True, "verification": {"date": "2026-09-09"}}}
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY": "mock-sensitive-token"}), patch.object(self.tools, "_provider_json", return_value=(200, payload)):
            result = self.tools.verify_email("jane@firm.example")
        self.assertEqual(result["status"], "catch_all")
        self.assertEqual(result["verified_at"], "2026-09-09")

    def test_pending_polling_honors_verification_budget(self):
        self.tools.request.enable_verification = True
        self.tools._published_emails.add("jane@firm.example")
        self.budget.limits["verifications"] = 1
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY": "mock-sensitive-token"}), patch.object(self.tools, "_provider_json", return_value=(202, {})) as provider, patch("time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "BudgetExceeded"):
                self.tools.verify_email("jane@firm.example")
        self.assertEqual(provider.call_count, 1)

    def test_optional_provider_failure_preserves_unverified_state(self):
        self.tools.request.enable_verification = True
        self.tools._published_emails.add("jane@firm.example")
        with patch.dict(os.environ, {"PROSPECT_RESEARCH_AGENT_HUNTER_API_KEY": "mock-sensitive-token"}), patch.object(self.tools, "_fetch", side_effect=lambda url, **kwargs: response(url, status=429, body=b"mock-sensitive-token")):
            result = self.tools.verify_email("jane@firm.example")
        self.assertEqual(result["status"], "published_unverified")
        self.assertIn("limit_or_access_failed", result["error"])
        self.assertNotIn("mock-sensitive-token", repr(result))


if __name__ == "__main__":
    unittest.main()
