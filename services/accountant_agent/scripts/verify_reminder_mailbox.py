"""Verify the isolated reminder OAuth identity without sending email."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overdue_reminder_agent.agent import reminder_gmail_config
from src.config import get_config
from src.email_client import GmailClient


gmail = GmailClient(reminder_gmail_config(get_config()))
profile = gmail._service.users().getProfile(userId="me").execute()
email = str(profile.get("emailAddress") or "").lower()
print(f"authorized_mailbox={email}")
print(f"mailbox_correct={email == 'accounts@menteso.com'}")
if email != "accounts@menteso.com":
    raise SystemExit("Reminder OAuth identity verification failed")
