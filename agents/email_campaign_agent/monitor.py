"""Supervised, bounded mailbox monitoring. This entry point cannot send email."""
import json
import time

from shared.config import PROJECT_ROOT
from shared.research_runtime import ResearchSession, _file_lock
from .models import Settings
from .runtime import monitor_once
from .store import Store


def run_monitor():
    started = time.monotonic()
    settings = Settings.from_env()
    store = Store(settings.state_dir)
    with _file_lock(settings.state_dir / 'monitor.lock'):
        session = ResearchSession('email_campaign_agent')
        session.load_memory()
        strategy = session.best_strategy('mailbox_monitor', 'standard')
        result = monitor_once(settings=settings, store=store)
        if result['emails_sent'] != 0 or result['campaigns_enabled'] is not False:
            raise RuntimeError('Monitor violated setup-only execution contract')
        healthy = result['mailbox_connected'] and not result.get('event_error')
        session.finish(result, 'success' if healthy else 'failure', strategy,
                       'Cursor commits follow durable message storage; ambiguous deliveries are never resent. '
                       + ('Connections verified.' if healthy else 'Missing or expired authorization needs operator attention.'),
                       time.monotonic() - started)
        return result


if __name__ == '__main__':
    result = run_monitor()
    # Mail subjects, bodies, recipients and tokens are deliberately absent from logs.
    print(json.dumps({'mailbox_connected': result['mailbox_connected'],
                      'events_processed': result['events_processed'], 'emails_sent': 0,
                      'campaigns_enabled': False}))
