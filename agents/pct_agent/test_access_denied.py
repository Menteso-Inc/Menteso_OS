from types import SimpleNamespace

from agents.pct_agent import browser


def test_http_403_stops_session_without_retry_or_reload(monkeypatch):
    calls = []
    monkeypatch.setattr(browser, '_pace', lambda: None)
    client = browser.PatentBrowser()
    client._page = SimpleNamespace(goto=lambda *a, **kw: calls.append(a) or SimpleNamespace(status=403))
    assert client.scrape_patent('https://example.org/one', 'one') is None
    assert client.scrape_patent('https://example.org/two', 'two') is None
    assert len(calls) == 1
    assert client.last_failure_reason == 'wipo_access_denied'


def test_forbidden_page_stops_polling_without_reload(monkeypatch):
    monkeypatch.setattr(browser, '_is_captcha_present', lambda *a: False)
    client = browser.PatentBrowser()
    client._page = SimpleNamespace(content=lambda: '<h1>Forbidden</h1>', title=lambda: '403 Forbidden')
    assert client._wait_for_content(timeout=1) is False
    assert client.access_denied and client.last_failure_reason == 'wipo_access_denied'
