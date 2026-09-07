"""Run under the shared systemd flock to serialize reminder state updates."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import get_config
from overdue_reminder_agent.agent import OverdueReminderAgent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-weekly", action="store_true")
    args = parser.parse_args()
    agent = OverdueReminderAgent(
        get_config(), "/home/menteso_os/data/accountant_agent/overdue-reminder-status.json"
    )
    # Detect replies and reconcile recorded payments before contacting clients.
    events = agent.monitor_activity()
    agent.reconcile_payments()
    singles = multiples = []
    if args.send_weekly:
        if not agent.state.get("weekly_schedule"):
            raise RuntimeError("Weekly schedule has not been configured")
        # Existing limits of 25 singles and 10 groups must not truncate the batch.
        singles = agent.send_live_singles(max_count=10000)
        multiples = agent.send_live_multiples(max_count=10000)
    else:
        agent.sync_dashboard()
    print(json.dumps({"activity_events": len(events), "singles_sent": len(singles),
                      "multiples_sent": len(multiples)}))


if __name__ == "__main__":
    main()
