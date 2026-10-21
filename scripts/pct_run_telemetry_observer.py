"""Replay one run's event journal into atomic dashboard telemetry snapshots.

This observer only reads events and publishes counters. It does not operate the
PCT worker, contact any provider, or access extraction/reference answers.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.pct_agent.telemetry import initialize, observe, public_metrics


def publish_snapshot(destination, payload):
    """Keep the last complete snapshot when Windows temporarily locks a file."""
    temporary = destination.with_name(destination.name + f'.{os.getpid()}.tmp')
    for attempt in range(6):
        try:
            with temporary.open('w', encoding='utf-8') as target:
                json.dump(payload, target)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, destination)
            return True
        except OSError as error:
            if not isinstance(error, PermissionError) and getattr(error, 'winerror', None) not in {5, 32, 33}:
                raise
            if attempt < 5:
                time.sleep(0.05 * 2 ** attempt)
    return False


def read_complete_record(stream):
    """Leave a partially written UTF-8 record untouched until its newline arrives."""
    offset = stream.tell()
    line = stream.readline()
    if not line.endswith(b'\n'):
        stream.seek(offset)
        return None
    return json.loads(line.decode('utf-8'))


def watch(events, destination, run_id, completion_file=None):
    metrics = initialize({})
    blocked = False
    # Replaying from zero on every observer restart reconstructs absolute totals.
    with events.open('rb') as stream:
        while True:
            record = read_complete_record(stream)
            if record is not None:
                stamp = datetime.fromisoformat(record['time']).timestamp() * 1000
                observe(metrics, record['event'], stamp)
                continue
            payload = {'run_id': run_id, **public_metrics(metrics),
                       'observerUpdatedAt': datetime.now(timezone.utc).isoformat()}
            published = publish_snapshot(destination, payload)
            if not published and not blocked:
                print('Telemetry snapshot is locked; keeping the previous snapshot and retrying.', file=sys.stderr, flush=True)
            elif published and blocked:
                print('Telemetry snapshot publishing recovered.', flush=True)
            blocked = not published
            if published and completion_file is not None and completion_file.exists():
                return
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--completion-file', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}', args.run_id):
        parser.error('Invalid run ID')
    watch(args.events, args.destination, args.run_id, args.completion_file)


if __name__ == '__main__':
    main()
