"""
scheduler_runner.py
Chạy riêng: python scheduler_runner.py
- Tự động đọc lại config mỗi lần chạy job → sếp đổi giờ trên app, có hiệu lực ngay lần gửi tiếp theo
- Chỉ gửi báo cáo nếu email SOC nhận được TRONG NGÀY HÔM ĐÓ
"""
import json
import logging
from pathlib import Path
from datetime import datetime, date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("soc_scheduler.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

CONFIG_FILE = Path("config/settings.json")
STATE_FILE  = Path("config/state.json")
LOG_FILE    = Path("config/logs.json")


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                content = f.read().strip()
            return json.loads(content) if content else {}
        except Exception:
            pass
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def append_log(action: str, detail: str, status: str = "success"):
    LOG_FILE.parent.mkdir(exist_ok=True)
    logs = []
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, encoding="utf-8") as f:
                content = f.read().strip()
            logs = json.loads(content) if content else []
        except Exception:
            logs = []
    logs.insert(0, {
        "time":   datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "action": action,
        "detail": detail,
        "status": status,
    })
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs[:200], f, ensure_ascii=False, indent=2)


def job_scan_email():
    """JOB 1: Quét email SOC, lưu state. Tự đọc config mới nhất mỗi lần chạy."""
    log.info("=== JOB: SCAN EMAIL ===")
    config    = load_config()  # đọc lại config mới nhất
    email_cfg = config.get("email", {})

    if not email_cfg.get("address") or not email_cfg.get("password"):
        log.warning("Email chưa được cấu hình. Bỏ qua.")
        return

    try:
        from utils.email_utils import connect_imap, search_soc_emails, parse_soc_email
        mail   = connect_imap(
            email_cfg["address"],
            email_cfg["password"],
            email_cfg.get("imap_server", "imap.gmail.com")
        )
        emails = search_soc_emails(mail, config.get("soc_sender_name", "SOC Canh bao"), limit=5)
        mail.logout()

        if not emails:
            log.info("Không tìm thấy email SOC.")
            append_log("SCAN_EMAIL", "Không tìm thấy email SOC", "warning")
            return

        latest = emails[0]
        parsed = parse_soc_email(latest["body"], latest.get("date", ""))
        log.info(f"Email mới nhất: {latest['subject']} | Chỉ số đỏ: {parsed['red_indicators']}")

        state = load_state()
        state["last_scan"]            = datetime.now().strftime("%d/%m/%Y %H:%M")
        state["last_scan_date"]       = date.today().strftime("%d/%m/%Y")  # lưu ngày quét
        state["total_scans"]          = state.get("total_scans", 0) + 1
        state["red_indicators"]       = parsed["red_indicators"]
        state["report_date"]          = parsed["report_date"]
        state["deadline"]             = parsed["deadline"]
        state["status"]               = "active"
        state["latest_email_sender"]  = latest["sender"]
        state["latest_email_subject"] = latest["subject"]
        state["latest_email_date"]    = latest.get("date", "")
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
    """
    JOB 2: Gửi báo cáo.
    - Tự đọc config mới nhất → sếp đổi giờ trên app có hiệu lực ngay
    - Chỉ gửi nếu đã quét được email SOC TRONG NGÀY HÔM NAY
    """
    log.info("=== JOB: SEND REPORT ===")
    config     = load_config()  # đọc lại config mới nhất
    state      = load_state()
    email_cfg  = config.get("email", {})
    sheets_cfg = config.get("google_sheets", {})

    # ── Kiểm tra: chỉ gửi nếu email SOC nhận được HÔM NAY ──
    today_str      = date.today().strftime("%d/%m/%Y")
    last_scan_date = state.get("last_scan_date", "")

    if last_scan_date != today_str:
        msg = f"Hôm nay ({today_str}) chưa nhận email SOC (quét gần nhất: {last_scan_date or 'chưa có'}). Bỏ qua gửi báo cáo."
        log.info(msg)
        append_log("AUTO_REPLY", msg, "warning")
        return

    red_indicators = state.get("red_indicators", [])
    if not red_indicators:
        log.info("Không có chỉ số đỏ hôm nay. Bỏ qua.")
        append_log("AUTO_REPLY", "Không có chỉ số đỏ hôm nay", "warning")
        return

    if not email_cfg.get("address") or not email_cfg.get("password"):
        log.warning("Email chưa cấu hình.")
        return

    try:
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
            explanations = [
                {"indicator": ind, "sheet_name": ind, "rows": [], "count": 0, "error": None}
                for ind in red_indicators
            ]

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

        state["last_email_sent"]   = datetime.now().strftime("%d/%m/%Y %H:%M")
        state["total_emails_sent"] = state.get("total_emails_sent", 0) + 1
        save_state(state)

        log.info(f"✅ Đã gửi báo cáo đến {to_address}")
        append_log("AUTO_REPLY", f"Gửi đến {to_address} – {len(red_indicators)} chỉ số đỏ", "success")

    except Exception as e:
        log.error(f"Lỗi gửi báo cáo: {e}")
        append_log("AUTO_REPLY", f"Lỗi: {str(e)}", "error")


def get_schedule_config():
    """Đọc cấu hình lịch từ file — dùng khi reschedule."""
    config     = load_config()
    sched_cfg  = config.get("scheduler", {})
    return (
        sched_cfg.get("scan_interval_minutes", 30),
        sched_cfg.get("reply_deadline_hour", 11),
        sched_cfg.get("reply_deadline_minute", 45),
    )


def job_check_and_reschedule(scheduler):
    """
    JOB 3: Kiểm tra mỗi 5 phút xem sếp có đổi giờ gửi trên app không.
    Nếu có → tự động cập nhật lịch mà không cần restart.
    """
    scan_interval, reply_h, reply_m = get_schedule_config()

    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    # Cập nhật giờ gửi báo cáo
    scheduler.reschedule_job(
        "send_report",
        trigger=CronTrigger(hour=reply_h, minute=reply_m, timezone="Asia/Ho_Chi_Minh")
    )
    # Cập nhật interval quét email
    scheduler.reschedule_job(
        "scan_email",
        trigger=IntervalTrigger(minutes=scan_interval)
    )
    log.debug(f"Config reloaded: quét mỗi {scan_interval}p, gửi lúc {reply_h:02d}:{reply_m:02d}")


def main():
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.error("APScheduler chưa cài. Chạy: pip install apscheduler")
        return

    scan_interval, reply_h, reply_m = get_schedule_config()

    scheduler = BlockingScheduler(timezone="Asia/Ho_Chi_Minh")

    # Job 1: Quét email định kỳ
    scheduler.add_job(
        job_scan_email,
        trigger=IntervalTrigger(minutes=scan_interval),
        id="scan_email",
        name="Quét Email SOC",
        replace_existing=True,
    )

    # Job 2: Gửi báo cáo hàng ngày
    scheduler.add_job(
        job_send_report,
        trigger=CronTrigger(hour=reply_h, minute=reply_m, timezone="Asia/Ho_Chi_Minh"),
        id="send_report",
        name="Gửi Báo cáo Tự động",
        replace_existing=True,
    )

    # Job 3: Kiểm tra config thay đổi mỗi 5 phút → tự cập nhật lịch
    scheduler.add_job(
        lambda: job_check_and_reschedule(scheduler),
        trigger=IntervalTrigger(minutes=5),
        id="check_config",
        name="Kiểm tra cấu hình",
        replace_existing=True,
    )

    log.info("=" * 50)
    log.info("SOC Scheduler khởi động")
    log.info(f"  Quét email  : mỗi {scan_interval} phút")
    log.info(f"  Gửi báo cáo : {reply_h:02d}:{reply_m:02d} hàng ngày")
    log.info(f"  Reload config: mỗi 5 phút (tự cập nhật khi sếp đổi giờ)")
    log.info("=" * 50)

    # Quét ngay khi khởi động
    job_scan_email()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler đã dừng.")


if __name__ == "__main__":
    main()