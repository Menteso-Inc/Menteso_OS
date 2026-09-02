from __future__ import annotations

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional


class ReminderSesSender:
    """Send agent-generated mail without writing to the Gmail Sent mailbox."""

    def __init__(self, region: str = "us-east-2", client=None):
        if client is None:
            import boto3
            client = boto3.client("sesv2", region_name=region)
        self.client = client
        self.from_address = "accounts@menteso.com"
        self.configuration_set = "invoice-reminder-agent"

    def send_message(
        self,
        to,
        subject: str,
        body_text: str,
        pdf_bytes: Optional[bytes] = None,
        pdf_filename: str = "invoice.pdf",
        html_body: Optional[str] = None,
        cc=None,
    ) -> str:
        recipients = [to] if isinstance(to, str) else list(to)
        cc_recipients = [] if cc is None else ([cc] if isinstance(cc, str) else list(cc))
        mime = MIMEMultipart("mixed")
        mime["To"] = ", ".join(recipients)
        if cc_recipients:
            mime["Cc"] = ", ".join(cc_recipients)
        mime["From"] = formataddr(("Menteso Accounts Team", self.from_address))
        mime["Reply-To"] = self.from_address
        mime["Subject"] = subject
        if html_body:
            alternative = MIMEMultipart("alternative")
            alternative.attach(MIMEText(body_text, "plain", "utf-8"))
            alternative.attach(MIMEText(html_body, "html", "utf-8"))
            mime.attach(alternative)
        else:
            mime.attach(MIMEText(body_text, "plain", "utf-8"))
        if pdf_bytes:
            attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
            attachment.add_header("Content-Disposition", "attachment", filename=pdf_filename)
            mime.attach(attachment)
        response = self.client.send_email(
            FromEmailAddress=self.from_address,
            Destination={"ToAddresses": recipients, "CcAddresses": cc_recipients},
            Content={"Raw": {"Data": mime.as_bytes()}},
            ConfigurationSetName=self.configuration_set,
            EmailTags=[{"Name": "agent", "Value": "invoice-reminder"}],
        )
        return response["MessageId"]
