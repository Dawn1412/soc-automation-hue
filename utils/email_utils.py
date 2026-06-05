"""
Email utilities: IMAP reading + SMTP sending
"""
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime, date
import re
import html
from typing import Optional


def decode_str(s):
    """Decode email header string."""
    if s is None:
        return ""
    decoded_parts = decode_header(s)
    result = ""
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(charset or "utf-8", errors="replace")
        else:
            result += str(part)
    return result


def connect_imap(address: str, password: str, server: str = "imap.gmail.com") -> imaplib.IMAP4_SSL:
    """Connect and login to IMAP server."""
    mail = imaplib.IMAP4_SSL(server)
    mail.login(address, password)
    return mail


def search_soc_emails(mail: imaplib.IMAP4_SSL, sender_name: str = "SOC Canh bao", limit: int = 10):
    """Search for SOC alert emails."""
    mail.select("INBOX")
    # Search by subject or from
    _, data = mail.search(None, f'(FROM "{sender_name}")')
    email_ids = data[0].split()
    email_ids = email_ids[-limit:]  # last N
    emails = []
    for eid in reversed(email_ids):
        _, msg_data = mail.fetch(eid, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        subject = decode_str(msg.get("Subject", ""))
        sender = decode_str(msg.get("From", ""))
        date_str = msg.get("Date", "")
        body = extract_body(msg)
        emails.append({
            "id": eid.decode(),
            "subject": subject,
            "sender": sender,
            "date": date_str,
            "body": body,
            "raw": msg,
        })
    return emails


def extract_body(msg) -> str:
    """Extract plain text or HTML body from email."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")
                break
            elif ctype == "text/html" and not body:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                body = html.unescape(re.sub(r"<[^>]+>", " ", payload.decode(charset, errors="replace")))
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        body = payload.decode(charset, errors="replace")
    return body


# ─── KPI indicator names (matching Google Sheets tabs) ──────────
KPI_INDICATORS = {
    "CSAT 1": ["CSAT 1", "csat1", "csat 1"],
    "Checklist lặp ≥ 3": ["Checklist lặp", "checklist lap", "CLL"],
    "PTC ≥ 72h": ["PTC", "ptc"],
    "Checklist ≥24h": ["Checklist 24h", "checklist 24"],
    "Yêu Cầu RM": ["Yêu Cầu RM", "yc rm", "YCRM"],
    "Yêu cầu khiếu nại": ["khiếu nại", "khieu nai"],
    "Yêu cầu ≥48h": ["yêu cầu 48h", "yc 48h"],
}


def parse_soc_email(body: str, email_date: str = "") -> dict:
    """
    Parse SOC alert email to extract:
    - Report date
    - Deadline
    - Red indicators (chỉ số đỏ)
    - Table data
    """
    result = {
        "report_date": None,
        "deadline": None,
        "red_indicators": [],
        "table_rows": [],
        "raw_body": body,
    }

    # Extract report date
    date_patterns = [
        r"(\d{2}/\d{2}/\d{4})",
        r"ngày\s+(\d{1,2}/\d{1,2}(?:/\d{4})?)",
        r"(\d{1,2})\s*[-–]\s*(\d{2})\s*[-–]\s*(\d{4})",
    ]
    for pat in date_patterns:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            result["report_date"] = m.group(0)
            break

    # Extract deadline
    deadline_m = re.search(r"trước\s+(\d{1,2}h\d{0,2})\s+ngày\s+(\d{1,2}/\d{1,2})", body, re.IGNORECASE)
    if deadline_m:
        result["deadline"] = f"{deadline_m.group(1)} ngày {deadline_m.group(2)}"

    # Detect red indicators by scanning for keyword + red markers
    lines = body.split("\n")
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        # Look for lines with numeric values that could be KPIs
        for indicator, keywords in KPI_INDICATORS.items():
            for kw in keywords:
                if kw.lower() in line_clean.lower():
                    # Heuristic: check if it contains numbers suggesting a problem
                    numbers = re.findall(r"\d+", line_clean)
                    if numbers:
                        # Check if non-zero (potential issue)
                        non_zero = [n for n in numbers if int(n) > 0]
                        if non_zero:
                            if indicator not in result["red_indicators"]:
                                result["red_indicators"].append(indicator)
                    break

    # Manual parsing of table rows
    table_pattern = re.compile(r"(\d+)\s+([\w\s≥≤≠ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠàáâãèéêìíòóôõùúăđĩũơƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂưăạảấầẩẫậắằẳẵặẹẻẽềềểỄỆỈỊỌỎỐỒổỗộớờởỡợụủứừửữựỳỵỷỹ\(\)\*]+?)\s+([\d/]+)", re.UNICODE)
    for m in table_pattern.finditer(body):
        result["table_rows"].append({
            "stt": m.group(1),
            "indicator": m.group(2).strip(),
            "value": m.group(3),
        })

    return result


def send_reply_email(
    smtp_server: str,
    address: str,
    password: str,
    to_address: str,
    subject: str,
    body_html: str,
    cc_list: list = None,
    reply_to_msg_id: str = None,
):
    """Send reply email via SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = address
    msg["To"] = to_address
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to_msg_id:
        msg["In-Reply-To"] = reply_to_msg_id
        msg["References"] = reply_to_msg_id

    part = MIMEText(body_html, "html", "utf-8")
    msg.attach(part)

    recipients = [to_address] + (cc_list or [])

    with smtplib.SMTP_SSL(smtp_server, 465) as server:
        server.login(address, password)
        server.sendmail(address, recipients, msg.as_string())

    return True


def test_imap_connection(address: str, password: str, server: str) -> tuple[bool, str]:
    """Test IMAP connection. Returns (success, message)."""
    try:
        mail = connect_imap(address, password, server)
        mail.logout()
        return True, "Kết nối IMAP thành công!"
    except Exception as e:
        return False, f"Lỗi IMAP: {str(e)}"


def test_smtp_connection(address: str, password: str, server: str) -> tuple[bool, str]:
    """Test SMTP connection."""
    try:
        with smtplib.SMTP_SSL(server, 465) as s:
            s.login(address, password)
        return True, "Kết nối SMTP thành công!"
    except Exception as e:
        return False, f"Lỗi SMTP: {str(e)}"
