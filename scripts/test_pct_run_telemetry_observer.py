import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.pct_run_telemetry_observer import publish_snapshot, read_complete_record, watch


class ObserverTests(unittest.TestCase):
    def test_transient_reader_lock_preserves_old_snapshot_until_atomic_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'telemetry.json'
            destination.write_text('{"sequence": 1}', encoding='utf-8')
            attempts = []
            replace = os.replace

            def reader_lock(source, target):
                attempts.append(1)
                self.assertEqual(json.loads(destination.read_text()), {'sequence': 1})
                if len(attempts) < 3:
                    raise PermissionError('Reader still holds the Windows file handle')
                return replace(source, target)

            with patch('scripts.pct_run_telemetry_observer.os.replace', side_effect=reader_lock), \
                    patch('scripts.pct_run_telemetry_observer.time.sleep'):
                self.assertTrue(publish_snapshot(destination, {'sequence': 2}))
            self.assertEqual(json.loads(destination.read_text()), {'sequence': 2})
            self.assertEqual(len(attempts), 3)

    def test_persistent_lock_keeps_valid_snapshot_and_can_recover_next_cycle(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'telemetry.json'
            destination.write_text('{"sequence": 1}', encoding='utf-8')
            with patch('scripts.pct_run_telemetry_observer.os.replace', side_effect=PermissionError('locked')), \
                    patch('scripts.pct_run_telemetry_observer.time.sleep'):
                self.assertFalse(publish_snapshot(destination, {'sequence': 2}))
            self.assertEqual(json.loads(destination.read_text()), {'sequence': 1})
            self.assertTrue(publish_snapshot(destination, {'sequence': 3}))
            self.assertEqual(json.loads(destination.read_text()), {'sequence': 3})

    def test_partial_unicode_event_is_consumed_exactly_once_when_complete(self):
        record = {'event': 'Reading PDF — row 20'}
        encoded = (json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8')
        split = encoded.index('—'.encode('utf-8')) + 1
        stream = io.BytesIO(encoded[:split])
        self.assertIsNone(read_complete_record(stream))
        self.assertEqual(stream.tell(), 0)
        stream.seek(0, io.SEEK_END)
        stream.write(encoded[split:])
        stream.seek(0)
        self.assertEqual(read_complete_record(stream), record)
        self.assertIsNone(read_complete_record(stream))

    def test_completed_run_retries_locked_final_snapshot_without_duplicate_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            events = root/'events.jsonl'
            events.write_text(json.dumps({'time': '2026-10-21T11:00:00+00:00',
                              'event': {'type': 'browser', 'event': 'captcha_detected'}}) + '\n')
            complete = root/'result.json'
            complete.write_text('{}')
            with patch('scripts.pct_run_telemetry_observer.publish_snapshot', side_effect=[False, True]) as publish, \
                    patch('scripts.pct_run_telemetry_observer.time.sleep'):
                watch(events, root/'telemetry.json', 'test-run', complete)
            self.assertEqual(publish.call_count, 2)
            for call in publish.call_args_list:
                self.assertEqual(call.args[1]['captchaDetected'], 1)
                self.assertEqual(call.args[1]['telemetrySequence'], 1)


if __name__ == '__main__':
    unittest.main()
