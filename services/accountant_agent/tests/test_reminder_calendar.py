from datetime import datetime, timedelta

from overdue_reminder_agent.agent import OverdueReminderAgent
from overdue_reminder_agent.schedule import weekly_due, next_weekly_follow_up


SCHEDULE = {"starts_at": "2026-09-07T20:00:00+05:30"}
START = datetime.fromisoformat(SCHEDULE["starts_at"])


def test_first_batch_resets_old_rolling_dates_without_sending_early():
    row = {"last_live_sent_at": "2026-09-03T05:38:51+00:00"}
    assert not weekly_due(SCHEDULE, row, START - timedelta(seconds=1))
    assert weekly_due(SCHEDULE, row, START)
    assert next_weekly_follow_up(SCHEDULE, row, START - timedelta(hours=1)) == START.isoformat()


def test_weekly_slot_deduplicates_and_does_not_drift_with_batch_duration():
    row = {"last_live_sent_at": (START + timedelta(minutes=8)).isoformat()}
    assert not weekly_due(SCHEDULE, row, START + timedelta(minutes=10))
    assert weekly_due(SCHEDULE, row, START + timedelta(days=7))
    assert next_weekly_follow_up(SCHEDULE, row, START + timedelta(minutes=10)) == (START + timedelta(days=7)).isoformat()


def test_no_sends_outside_monday_batch_window():
    for delta in [timedelta(hours=1), timedelta(days=1), timedelta(days=6)]:
        assert not weekly_due(SCHEDULE, {}, START + delta)
    assert next_weekly_follow_up(SCHEDULE, {}, START + timedelta(days=1)) == (START + timedelta(days=7)).isoformat()


def test_fixed_schedule_keeps_global_and_customer_pauses():
    agent = object.__new__(OverdueReminderAgent)
    agent.state = {"weekly_schedule": SCHEDULE, "customers": {"c": {}}}
    assert agent.due_for_follow_up("c", START)
    agent.state["paused"] = True
    assert not agent.due_for_follow_up("c", START)
    agent.state["paused"] = False
    agent.state["customers"]["c"]["paused"] = True
    assert not agent.due_for_follow_up("c", START)
