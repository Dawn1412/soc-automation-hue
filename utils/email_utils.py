"""
Email utilities: IMAP reading + SMTP sending
Fix: tự động lấy email SOC MỚI NHẤT theo ngày thực tế từ header
"""
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, date, timezone
import re
import html
from typing import Optional


def decode_str(s):
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
    mail = imaplib.IMAP4_SSL(server)
    mail.login(address, password)
    return mail


def parse_email_date(date_str: str) -> Optional[datetime]:
    """
    Parse email Date header thành datetime (aware, UTC).
    Trả về None nếu không parse được.
    """
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        # Đảm bảo có timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def search_soc_emails(
    mail: imaplib.IMAP4_SSL,
    sender_name: str = "SOC Canh bao",
    limit: int = 10
) -> list[dict]:
    """
    Tìm email từ SOC, sắp xếp theo ngày IMAP header (mới nhất trước).
    Trả về list dict, phần tử [0] luôn là email MỚI NHẤT.
    """
    mail.select("INBOX")
    _, data = mail.search(None, f'(FROM "{sender_name}")')
    email_ids = data[0].split()
    if not email_ids:
        return []

    # Lấy nhiều hơn limit để sau khi sort vẫn còn đủ
    fetch_ids = email_ids[-(limit * 2):]

    raw_emails = []
    for eid in fetch_ids:
        _, msg_data = mail.fetch(eid, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        date_str = msg.get("Date", "")
        parsed_dt = parse_email_date(date_str)

        subject = decode_str(msg.get("Subject", ""))
        sender  = decode_str(msg.get("From", ""))
        body    = extract_body(msg)

        raw_emails.append({
            "id":         eid.decode(),
            "subject":    subject,
            "sender":     sender,
            "date":       date_str,
            "parsed_dt":  parsed_dt,   # datetime object để sort
            "body":       body,
            "raw":        msg,
        })

    # Sắp xếp: mới nhất trước (None date xuống cuối)
    raw_emails.sort(
        key=lambda e: e["parsed_dt"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True
    )

    return raw_emails[:limit]


def get_latest_soc_email(
    mail: imaplib.IMAP4_SSL,
    sender_name: str = "SOC Canh bao"
) -> Optional[dict]:
    """
    Trả về DUY NHẤT 1 email SOC mới nhất.
    Dùng cho scheduler và auto-reply.
    """
    emails = search_soc_emails(mail, sender_name, limit=1)
    return emails[0] if emails else None


def extract_body(msg) -> str:
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
                body = html.unescape(
                    re.sub(r"<[^>]+>", " ",
                           payload.decode(charset, errors="replace"))
                )
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        body = payload.decode(charset, errors="replace")
    return body


# ─── KPI indicators ───────────────────────────────────────────────
KPI_INDICATORS = {
    "CSAT 1":              ["CSAT 1", "csat1", "csat 1"],
    "Checklist lặp ≥ 3":  ["Checklist lặp", "checklist lap", "CLL"],
    "PTC ≥ 72h":           ["PTC", "ptc"],
    "Checklist ≥24h":      ["Checklist 24h", "checklist 24"],
    "Yêu Cầu RM":          ["Yêu Cầu RM", "yc rm", "YCRM"],
    "Yêu cầu khiếu nại":   ["khiếu nại", "khieu nai"],
    "Yêu cầu ≥48h":        ["yêu cầu 48h", "yc 48h"],
}


def parse_soc_email(body: str, email_date: str = "") -> dict:
    """
    Parse SOC alert email:
    - report_date: ưu tiên lấy từ email_date header (chính xác nhất)
    - Fallback: tìm trong body
    - red_indicators: nhận diện chỉ số đỏ
    """
    result = {
        "report_date":     None,
        "report_date_obj": None,   # datetime object cho việc so sánh
        "deadline":        None,
        "red_indicators":  [],
        "table_rows":      [],
        "raw_body":        body,
        "email_received":  email_date,  # lưu lại header gốc
    }

    # ── 1. Lấy report_date từ email Date header (ưu tiên cao nhất) ──
    if email_date:
        dt = parse_email_date(email_date)
        if dt:
            result["report_date_obj"] = dt
            # Format thành dd/mm/yyyy cho hiển thị
            result["report_date"] = dt.strftime("%d/%m/%Y")

    # ── 2. Fallback: tìm ngày trong body ──
    if not result["report_date"]:
        date_patterns = [
            r"(\d{2}/\d{2}/\d{4})",
            r"ngày\s+(\d{1,2}/\d{1,2}(?:/\d{4})?)",
        ]
        for pat in date_patterns:
            m = re.search(pat, body, re.IGNORECASE)
            if m:
                result["report_date"] = m.group(1) if m.lastindex else m.group(0)
                break

    # ── 3. Deadline ──
    deadline_m = re.search(
        r"trước\s+(\d{1,2}h\d{0,2})\s+ngày\s+(\d{1,2}/\d{1,2})",
        body, re.IGNORECASE
    )
    if deadline_m:
        result["deadline"] = f"{deadline_m.group(1)} ngày {deadline_m.group(2)}"

    # ── 4. Nhận diện chỉ số đỏ ──
    lines = body.split("\n")
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        for indicator, keywords in KPI_INDICATORS.items():
            for kw in keywords:
                if kw.lower() in line_clean.lower():
                    numbers = re.findall(r"\d+", line_clean)
                    if numbers and any(int(n) > 0 for n in numbers):
                        if indicator not in result["red_indicators"]:
                            result["red_indicators"].append(indicator)
                    break

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
    excel_attachment: bytes = None,
    excel_filename: str = "giai_trinh.xlsx",
):
    from email.mime.base import MIMEBase
    from email import encoders

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = address
    msg["To"]      = to_address
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to_msg_id:
        msg["In-Reply-To"] = reply_to_msg_id
        msg["References"]  = reply_to_msg_id

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(alt)

    if excel_attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(excel_attachment)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{excel_filename}"')
        msg.attach(part)

    recipients = [to_address] + (cc_list or [])
    with smtplib.SMTP_SSL(smtp_server, 465) as server:
        server.login(address, password)
        server.sendmail(address, recipients, msg.as_bytes())
    return True


def test_imap_connection(address: str, password: str, server: str) -> tuple[bool, str]:
    try:
        mail = connect_imap(address, password, server)
        mail.logout()
        return True, "Kết nối IMAP thành công!"
    except Exception as e:
        return False, f"Lỗi IMAP: {str(e)}"


def test_smtp_connection(address: str, password: str, server: str) -> tuple[bool, str]:
    try:
        with smtplib.SMTP_SSL(server, 465) as s:
            s.login(address, password)
        return True, "Kết nối SMTP thành công!"
    except Exception as e:
        return False, f"Lỗi SMTP: {str(e)}"