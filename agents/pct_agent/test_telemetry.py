import ast
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from agents.pct_agent.telemetry import observe, public_metrics
from agents.pct_agent.captcha_solver.manual_fallback import _patent_page_ready


class TelemetryTests(unittest.TestCase):
    def test_real_server_snapshot_accumulates_captcha_events(self):
        # Execute the actual status reducer without starting the monolithic
        # server, schedulers, database or any providers.
        source = Path(__file__).resolve().parents[2] / 'server.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        names = {'_append_live_log', '_update_live_status'}
        tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        scope = dict(RUN_LIVE_STATUS={}, datetime=datetime, timezone=timezone, re=re)
        exec(compile(tree, str(source), 'exec'), scope)
        update = scope['_update_live_status']
        update('pct_agent', {'type': 'browser', 'event': 'captcha_detected'})
        update('pct_agent', {'type': 'browser', 'event': 'solver_succeeded', 'tier': 'manual', 'confirmed': True})
        update('pct_agent', {'type': 'browser', 'event': 'captcha_cleared'})
        metrics = scope['RUN_LIVE_STATUS']['pct_agent']['metrics']
        self.assertEqual(metrics['captchaTotals'], {'manual': 1})
        self.assertEqual(metrics['captchaCount'], 1)
        self.assertEqual(metrics['captchaUnconfirmedCount'], 0)
        update('other_agent', 'unchanged')
        self.assertNotIn('telemetryVersion', scope['RUN_LIVE_STATUS']['other_agent']['metrics'])

    def test_failures_are_not_successes(self):
        metrics = {}
        for kind, text in [('captcha_detected', ''), ('solver_failed_escalating', ''),
                           ('captcha_cleared', '[Solver] All tiers exhausted — giving up')]:
            observe(metrics, {'type': 'browser', 'event': kind, 'message': text})
        self.assertEqual(metrics['captchaCount'], 0)
        self.assertEqual(metrics['captchaDetected'], 1)
        self.assertEqual(metrics['captchaFailures'], 1)
        self.assertEqual(metrics['captchaState'], 'failed')

    def test_absolute_snapshots_and_legacy_uncertainty(self):
        metrics = {}
        for confirmed in (False, True):
            observe(metrics, {'type': 'browser', 'event': 'solver_succeeded',
                              'tier': 'manual', 'confirmed': confirmed})
        snapshot = public_metrics(metrics)
        self.assertEqual(snapshot['captchaCount'], 2)
        self.assertEqual(snapshot['captchaTotals'], {'manual': 2})
        self.assertEqual(snapshot['captchaUnconfirmedCount'], 1)
        observe(metrics, {'type': 'browser', 'event': 'solver_succeeded', 'tier': 'vision'})
        self.assertEqual(snapshot['captchaCount'], 2)
        self.assertNotIn('vision', snapshot['captchaTotals'])

    def test_overlapping_activity_and_download_errors(self):
        metrics = {}
        observe(metrics, '[Row 4] [PDF Extractor] Extracting and verifying downloaded PDF', 1000)
        observe(metrics, '[Row 5/100] Downloading: synthetic', 2000)
        self.assertEqual(metrics['verificationRows'], [4])
        self.assertEqual(metrics['downloadingRow'], 5)
        observe(metrics, '[Row 4] [AI Verification] Reading 3 original PDF page(s)', 3000)
        self.assertEqual(metrics['verificationStartedAt'], {'4': 1000})
        observe(metrics, {'type': 'browser', 'event': 'contacts', 'row': 5, 'status': 'error'}, 4000)
        self.assertEqual(metrics['successfulRowTimestamps'], [])
        self.assertEqual(metrics['verificationRows'], [4])
        observe(metrics, {'type': 'browser', 'event': 'contacts', 'row': 4, 'status': 'found'}, 5000)
        self.assertEqual(metrics['successfulRowTimestamps'], [5000])
        self.assertEqual(metrics['verificationRows'], [])

    def test_success_window_bounded(self):
        metrics = {}
        for i in range(50):
            observe(metrics, {'type': 'browser', 'event': 'contacts', 'row': i, 'status': 'found'}, i)
        self.assertEqual(metrics['successfulRowTimestamps'], list(range(30, 50)))


class ManualConfirmationTests(unittest.TestCase):
    def page(self, visible=False):
        page = Mock()
        page.is_closed.return_value = False
        page.title.return_value = 'Patent details'
        page.locator.return_value.count.return_value = int(visible)
        page.locator.return_value.first.is_visible.return_value = visible
        page.get_by_text.return_value.first.is_visible.return_value = False
        return page

    def ready(self, page, challenge=False):
        with patch('agents.pct_agent.captcha_solver.manual_fallback._form_visible', return_value=False), \
             patch('agents.pct_agent.browser._page_has_captcha_selectors', return_value=challenge), \
             patch('agents.pct_agent.browser._title_looks_like_captcha', return_value=False):
            return _patent_page_ready(page)

    def test_blank_page_is_not_solved(self):
        self.assertFalse(self.ready(self.page()))

    def test_closed_or_error_page_is_not_solved(self):
        page = self.page(True)
        page.is_closed.return_value = True
        self.assertFalse(self.ready(page))
        page.is_closed.return_value = False
        page.title.return_value = '403 Forbidden'
        self.assertFalse(self.ready(page))

    def test_remaining_challenge_is_not_solved(self):
        self.assertFalse(self.ready(self.page(True), challenge=True))

    def test_visible_patent_page_is_ready(self):
        self.assertTrue(self.ready(self.page(True)))

    def test_browser_exception_is_not_success(self):
        page = self.page(True)
        page.title.side_effect = RuntimeError('closed')
        self.assertFalse(self.ready(page))


if __name__ == '__main__':
    unittest.main()
