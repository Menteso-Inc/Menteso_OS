import os
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value):
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _file_size_mb(path):
    try:
        return Path(path).stat().st_size / (1024 * 1024)
    except Exception:
        return 0


def _work_label(gazette, input_name):
    gazette = str(gazette or "").strip()
    input_name = str(input_name or "").strip()
    if gazette:
        return f"WIPO gazette/week {gazette}"
    if input_name:
        return f"uploaded sheet {input_name}"
    return "PCT work sheet"


def send_pct_completion_email(result):
    """Send a compact PCT completion email.

    The PCT sheet/contact data remains local. The email may attach the local
    output file when it is small enough for SMTP; otherwise it sends the local
    path and summary only.
    """
    if not _truthy(os.getenv("PCT_EMAIL_ENABLED")):
        return {"sent": False, "reason": "disabled"}

    host = os.getenv("PCT_EMAIL_SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("PCT_EMAIL_SMTP_PORT", "587") or "587")
    user = os.getenv("PCT_EMAIL_SMTP_USER", "").strip()
    password = os.getenv("PCT_EMAIL_SMTP_PASSWORD", "").strip()
    from_addr = os.getenv("PCT_EMAIL_FROM", user).strip()
    recipients = _split_csv(os.getenv("PCT_EMAIL_TO"))
    max_mb = float(os.getenv("PCT_EMAIL_MAX_ATTACHMENT_MB", "20") or "20")

    if not host or not port or not user or not password or not from_addr or not recipients:
        return {"sent": False, "reason": "missing_email_config"}

    summary = result.get("summary") if isinstance(result, dict) else {}
    output_file = str((result or {}).get("output_file") or "").strip()
    not_found_file = str((result or {}).get("not_found_file") or "").strip()
    input_name = str((result or {}).get("input_file_name") or "").strip()
    gazette = str((result or {}).get("gazette") or "").strip()
    work_label = _work_label(gazette, input_name)
    status = str((result or {}).get("status") or "unknown").strip()
    execution_time = result.get("execution_time", result.get("executionTime", "")) if isinstance(result, dict) else ""

    subject = f"PCT Agent completed - {work_label}"

    output_name = Path(output_file).name if output_file else "N/A"
    not_found_name = Path(not_found_file).name if not_found_file else "N/A"
    output_folder = str(Path(output_file).parent) if output_file else "N/A"
    public_base_url = str(os.getenv("PUBLIC_BASE_URL") or os.getenv("APP_BASE_URL") or "").strip().rstrip("/")
    dashboard_url = public_base_url or "N/A"
    download_url = (
        f"{public_base_url}/api/download/{quote(output_name)}"
        if public_base_url and output_file and output_name != "N/A"
        else "N/A"
    )
    body_lines = [
        "PCT Agent work completed on the server.",
        "",
        f"Work: {work_label}",
        f"Status: {status}",
        f"Input sheet: {input_name or 'N/A'}",
        f"Gazette/week: {gazette or 'N/A'}",
        f"Total rows: {summary.get('total', 0)}",
        f"Processed rows: {summary.get('processed', 0)}",
        f"Found: {summary.get('found', 0)}",
        f"Not found: {summary.get('not_found', 0)}",
        f"Errors: {summary.get('errors', 0)}",
        f"Execution time: {execution_time}s",
        f"Worked file: {output_name}",
        f"Not-found file: {not_found_name}",
        f"Output folder: {output_folder}",
        f"Saved on server: {output_file or 'N/A'}",
        f"Dashboard link: {dashboard_url}",
        f"Download link: {download_url}",
        f"Email generated: {datetime.now(timezone.utc).isoformat()}",
    ]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    # Attach BOTH deliverables (worked + not-found). Decide which fit under the
    # SMTP size limit up front, finalize the body once, then attach.
    to_attach = []
    skipped = []
    for fpath in (output_file, not_found_file):
        if not fpath or not Path(fpath).exists():
            continue
        size_mb = _file_size_mb(fpath)
        if size_mb <= max_mb:
            to_attach.append(fpath)
        else:
            skipped.append(f"{Path(fpath).name} ({size_mb:.2f}MB)")

    if skipped:
        body_lines.append("")
        body_lines.append(f"Attachment(s) skipped (over {max_mb:.2f} MB limit): {', '.join(skipped)}.")

    msg.set_content("\n".join(body_lines))

    for fpath in to_attach:
        msg.add_attachment(
            Path(fpath).read_bytes(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=Path(fpath).name,
        )

    attached = bool(to_attach)
    skipped_attachment_reason = ("attachment_too_large:" + ", ".join(skipped)) if skipped else ""

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)

    return {
        "sent": True,
        "to": recipients,
        "attached": attached,
        "attachedFiles": [Path(f).name for f in to_attach],
        "skippedAttachmentReason": skipped_attachment_reason,
    }
