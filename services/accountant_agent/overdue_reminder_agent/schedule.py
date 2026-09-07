"""Fixed weekly reminder slots, independent of previous batch duration."""
from datetime import datetime, timedelta


def weekly_slot(schedule, now):
    anchor = datetime.fromisoformat(schedule["starts_at"])
    if now < anchor:
        return anchor
    return anchor + ((now - anchor) // timedelta(days=7)) * timedelta(days=7)


def weekly_due(schedule, row, now):
    slot = weekly_slot(schedule, now)
    if not slot <= now < slot + timedelta(hours=1):
        return False
    last = row.get("last_live_sent_at")
    return not last or datetime.fromisoformat(last.replace("Z", "+00:00")) < slot


def next_weekly_follow_up(schedule, row, now):
    slot = weekly_slot(schedule, now)
    if now < slot or weekly_due(schedule, row, now):
        return slot.isoformat()
    return (slot + timedelta(days=7)).isoformat()
