"""Run-scoped counters and activity, shared by live status and log replay.

No contact values, model calls, browser operations or result changes belong here.
"""
import re
import time
from copy import deepcopy
from threading import RLock

LOCK = RLock()
KEYS = ('telemetryVersion', 'telemetrySequence', 'captchaCount', 'captchaTotals',
        'captchaDetected', 'captchaFailures', 'captchaActive', 'captchaState',
        'captchaUnconfirmedCount', 'verificationRows', 'verificationStartedAt',
        'downloadingRow', 'successfulRowTimestamps', 'lastActivityAt')


def initialize(metrics):
    defaults = dict(telemetryVersion=1, telemetrySequence=0, captchaCount=0,
                    captchaTotals={}, captchaDetected=0, captchaFailures=0,
                    captchaActive=False, captchaState='none', captchaUnconfirmedCount=0,
                    verificationRows=[], verificationStartedAt={}, downloadingRow=None,
                    successfulRowTimestamps=[], lastActivityAt=None)
    for key, value in defaults.items():
        metrics.setdefault(key, value)
    return metrics


def public_metrics(metrics):
    with LOCK:
        return deepcopy({key: metrics[key] for key in KEYS if key in metrics})


def observe(metrics, event, now_ms=None):
    """Consume each original event once; clients receive absolute snapshots."""
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    with LOCK:
        initialize(metrics)
        metrics['telemetrySequence'] += 1
        message = str(event.get('message') or '') if isinstance(event, dict) else str(event)
        row_match = re.search(r'\[Row (\d+)(?:/\d+)?\]', message)
        row = int(row_match.group(1)) if row_match else None
        if row and 'Downloading:' in message:
            metrics['downloadingRow'] = row
        if '[Browser] PDF saved:' in message:
            metrics['downloadingRow'] = None
        if row and ('Extracting and verifying downloaded PDF' in message
                    or '[AI Verification] Reading ' in message):
            if row not in metrics['verificationRows']:
                metrics['verificationRows'].append(row)
            metrics['verificationStartedAt'].setdefault(str(row), now_ms)
        if not isinstance(event, dict) or event.get('type') != 'browser':
            if message:
                metrics['lastActivityAt'] = now_ms
            return
        kind = event.get('event')
        if kind == 'captcha_detected':
            metrics['captchaDetected'] += 1
            metrics['captchaActive'] = True
            metrics['captchaState'] = 'waiting'
        elif kind == 'solver_succeeded':
            tier = str(event.get('tier') or 'other').lower()
            metrics['captchaTotals'][tier] = metrics['captchaTotals'].get(tier, 0) + 1
            metrics['captchaCount'] += 1
            if not event.get('confirmed'):
                metrics['captchaUnconfirmedCount'] += 1
            metrics['captchaState'] = 'cleared'
            metrics['captchaActive'] = False
        elif kind == 'captcha_failed' or (kind == 'captcha_cleared'
                                         and 'All tiers exhausted' in message):
            metrics['captchaFailures'] += 1
            metrics['captchaActive'] = False
            metrics['captchaState'] = 'failed'
        elif kind == 'captcha_cleared':
            metrics['captchaActive'] = False
        elif kind in {'contacts', 'no_pdf'}:
            completed = event.get('row')
            metrics['verificationRows'] = [r for r in metrics['verificationRows'] if r != completed]
            metrics['verificationStartedAt'].pop(str(completed), None)
            if metrics['downloadingRow'] == completed:
                metrics['downloadingRow'] = None
            # Failed downloads are not samples of verified-PDF throughput.
            if event.get('status') in {'found', 'not_found'} or kind == 'no_pdf':
                stamps = metrics['successfulRowTimestamps']
                stamps.append(now_ms)
                del stamps[:-20]
        metrics['lastActivityAt'] = now_ms
