"""
scheduler_runner.py
Chạy riêng: python scheduler_runner.py
APScheduler chạy nền: quét email + gửi báo cáo tự động
"""
import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("soc_scheduler.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

CONFIG_FILE = Path("config/settings.json")
STATE_FILE = Path("config/state.json")
LOG_FILE = Path("config/logs.json")


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def append_log(action: str, detail: str, status: str = "success"):
    LOG_FILE.parent.mkdir(exist_ok=True)
    logs = []
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            logs = json.load(f)
    logs.insert(0, {
        "time": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "action": action,
        "detail": detail,
        "status": status,
    })
    with open(LOG_FILE, "w") as f:
        json.dump(logs[:200], f, ensure_ascii=False, indent=2)


def job_scan_email():
    """JOB 1: Quét email SOC và lưu kết quả vào state."""
    log.info("=== JOB: SCAN EMAIL ===")
    config = load_config()
    email_cfg = config.get("email", {})

    if not email_cfg.get("address") or not email_cfg.get("password"):
        log.warning("Email chưa được cấu hình. Bỏ qua.")
        return

    try:
        from utils.email_utils import connect_imap, search_soc_emails, parse_soc_email
        mail = connect_imap(
            email_cfg["address"],
            email_cfg["password"],
            email_cfg.get("imap_server", "imap.gmail.com")
        )
        emails = search_soc_emails(mail, config.get("soc_sender_name", "SOC Canh bao"), limit=5)
        mail.logout()

        if not emails:
            log.info("Không tìm thấy email SOC mới.")
            append_log("SCAN_EMAIL", "Không tìm thấy email SOC mới", "warning")
            return

        latest = emails[0]
        parsed = parse_soc_email(latest["body"])
        log.info(f"Tìm thấy {len(emails)} email. Chỉ số đỏ: {parsed['red_indicators']}")

        state = load_state()
        state["last_scan"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        state["total_scans"] = state.get("total_scans", 0) + 1
        state["red_indicators"] = parsed["red_indicators"]
        state["report_date"] = parsed["report_date"]
        state["deadline"] = parsed["deadline"]
        state["status"] = "active"
        state["latest_email_sender"] = latest["sender"]
        state["latest_email_subject"] = latest["subject"]
        save_state(state)

        append_log(
            "SCAN_EMAIL",
            f"Tìm thấy {len(emails)} email. {len(parsed['red_indicators'])} chỉ số đỏ: {', '.join(parsed['red_indicators'])}",
            "success"
        )

    except Exception as e:
        log.error(f"Lỗi scan email: {e}")
        append_log("SCAN_EMAIL", f"Lỗi: {str(e)}", "error")


def job_send_report():
    """JOB 2: Tổng hợp Sheets và gửi email phản hồi."""
    log.info("=== JOB: SEND REPORT ===")
    config = load_config()
    state = load_state()
    email_cfg = config.get("email", {})
    sheets_cfg = config.get("google_sheets", {})

    red_indicators = state.get("red_indicators", [])
    if not red_indicators:
        log.info("Không có chỉ số đỏ. Bỏ qua gửi báo cáo.")
        return

    if not email_cfg.get("address") or not email_cfg.get("password"):
        log.warning("Email chưa cấu hình.")
        return

    try:
        # Collect explanations
        explanations = []
        if sheets_cfg.get("credentials_path"):
            from utils.sheets_utils import collect_all_explanations
            explanations = collect_all_explanations(
                sheets_cfg["credentials_path"],
                sheets_cfg.get("spreadsheet_id", ""),
                red_indicators,
                state.get("report_date", "")
            )
        else:
            explanations = [{"indicator": ind, "sheet_name": ind, "rows": [], "count": 0, "error": None} for ind in red_indicators]

        # Build email
        from utils.sheets_utils import build_email_html
        html_body = build_email_html(
            state.get("report_date", "N/A"),
            config.get("branch", "HUE"),
            explanations
        )

        to_address = state.get("latest_email_sender", "")
        if not to_address:
            log.warning("Không có địa chỉ nhận. Bỏ qua.")
            return

        subject = f"Re: {state.get('latest_email_subject', 'SOC Canh bao')} – Giải trình {state.get('report_date', '')}"

        from utils.email_utils import send_reply_email
        send_reply_email(
            smtp_server=email_cfg.get("smtp_server", "smtp.gmail.com"),
            address=email_cfg["address"],
            password=email_cfg["password"],
            to_address=to_address,
            subject=subject,
            body_html=html_body,
        )

        state["last_email_sent"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        state["total_emails_sent"] = state.get("total_emails_sent", 0) + 1
        save_state(state)

        log.info(f"Đã gửi báo cáo đến {to_address}")
        append_log("AUTO_REPLY", f"Gửi đến {to_address} – {len(red_indicators)} chỉ số đỏ", "success")

    except Exception as e:
        log.error(f"Lỗi gửi báo cáo: {e}")
        append_log("AUTO_REPLY", f"Lỗi: {str(e)}", "error")


def main():
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.error("APScheduler chưa cài. Chạy: pip install apscheduler")
        return

    config = load_config()
    sched_cfg = config.get("scheduler", {})
    scan_interval = sched_cfg.get("scan_interval_minutes", 30)
    reply_h = sched_cfg.get("reply_deadline_hour", 11)
    reply_m = sched_cfg.get("reply_deadline_minute", 45)

    scheduler = BlockingScheduler(timezone="Asia/Ho_Chi_Minh")

    # Job 1: Quét email định kỳ
    scheduler.add_job(
        job_scan_email,
        trigger=IntervalTrigger(minutes=scan_interval),
        id="scan_email",
        name="Quét Email SOC",
        replace_existing=True,
    )

    # Job 2: Gửi báo cáo hàng ngày trước deadline
    scheduler.add_job(
        job_send_report,
        trigger=CronTrigger(hour=reply_h, minute=reply_m, timezone="Asia/Ho_Chi_Minh"),
        id="send_report",
        name="Gửi Báo cáo Tự động",
        replace_existing=True,
    )

    log.info(f"Scheduler khởi động:")
    log.info(f"  - Quét email: mỗi {scan_interval} phút")
    log.info(f"  - Gửi báo cáo: {reply_h:02d}:{reply_m:02d} hàng ngày (Asia/Ho_Chi_Minh)")
    log.info("Nhấn Ctrl+C để dừng.")

    # Run immediately on start
    job_scan_email()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler đã dừng.")


if __name__ == "__main__":
    main()
