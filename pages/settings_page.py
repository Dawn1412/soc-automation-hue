"""Settings page"""
import streamlit as st
import json
from pathlib import Path

def render(config: dict, save_config):
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>⚙️ Cấu hình Hệ thống</h1>
            <div class="subtitle">Thiết lập email, Google Sheets, và thông số hoạt động</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["📧  Email", "📊  Google Sheets", "🏢  Hệ thống", "🔑  Kết nối test"])

    with tab1:
        st.markdown("<br>", unsafe_allow_html=True)
        email_cfg = config.get("email", {})

        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="config-section"><h4>TÀI KHOẢN ADMIN</h4>', unsafe_allow_html=True)
            address = st.text_input("Địa chỉ email (Admin)", value=email_cfg.get("address", ""), placeholder="admin@gmail.com")
            password = st.text_input("Mật khẩu / App Password", value=email_cfg.get("password", ""), type="password", placeholder="Dùng App Password nếu bật 2FA")
            st.markdown("</div>", unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="config-section"><h4>MÁY CHỦ EMAIL</h4>', unsafe_allow_html=True)
            imap_server = st.text_input("IMAP Server", value=email_cfg.get("imap_server", "imap.gmail.com"))
            smtp_server = st.text_input("SMTP Server", value=email_cfg.get("smtp_server", "smtp.gmail.com"))
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("""
        <div class="alert-box info" style="font-size:12px;">
            💡 <strong>Gmail:</strong> Bật "Quyền truy cập ứng dụng kém an toàn" hoặc dùng <strong>App Password</strong> (Tài khoản Google → Bảo mật → Xác minh 2 bước → Mật khẩu ứng dụng).
            IMAP: <code>imap.gmail.com</code> | SMTP: <code>smtp.gmail.com</code>
        </div>
        """, unsafe_allow_html=True)

        if st.button("💾 Lưu cấu hình Email", type="primary"):
            config["email"] = {
                "address": address,
                "password": password,
                "imap_server": imap_server,
                "smtp_server": smtp_server,
            }
            save_config(config)
            st.markdown('<div class="alert-box success">✅ Đã lưu cấu hình email!</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown("<br>", unsafe_allow_html=True)
        sheets_cfg = config.get("google_sheets", {})

        st.markdown('<div class="config-section"><h4>GOOGLE SHEETS</h4>', unsafe_allow_html=True)
        spreadsheet_id = st.text_input(
            "Spreadsheet ID",
            value=sheets_cfg.get("spreadsheet_id", "11A4TuYjE3iLU92IvYK3UlOclB2baOd7Yawd4LyGrsW8"),
            help="Lấy từ URL: https://docs.google.com/spreadsheets/d/[ID]/edit"
        )
        
        creds_path = st.text_input(
            "Đường dẫn Service Account JSON",
            value=sheets_cfg.get("credentials_path", ""),
            placeholder="/path/to/service-account.json",
            help="Tạo từ Google Cloud Console → Service Account → JSON Key"
        )

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("""
        <div class="alert-box info" style="font-size:12px;">
            💡 <strong>Tạo Service Account:</strong><br>
            1. Vào <a href="https://console.cloud.google.com/" target="_blank" style="color:#90CDF4;">Google Cloud Console</a><br>
            2. APIs & Services → Enable: Google Sheets API, Google Drive API<br>
            3. Credentials → Create Service Account → JSON Key<br>
            4. Chia sẻ Google Sheet với email của Service Account (Editor access)
        </div>
        """, unsafe_allow_html=True)

        # Sheet mapping editor
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("✏️ Chỉnh sửa ánh xạ Chỉ số → Tab Sheet"):
            from utils.sheets_utils import INDICATOR_TO_SHEET
            mapping_text = "\n".join(f"{k}={v}" for k, v in INDICATOR_TO_SHEET.items())
            new_mapping = st.text_area("Định dạng: Tên chỉ số=Tên tab", value=mapping_text, height=200)
            st.caption("Mỗi dòng: Tên chỉ số=Tên tab trong Google Sheets")

        if st.button("💾 Lưu cấu hình Sheets", type="primary"):
            config["google_sheets"] = {
                "spreadsheet_id": spreadsheet_id,
                "credentials_path": creds_path,
            }
            save_config(config)
            st.markdown('<div class="alert-box success">✅ Đã lưu cấu hình Google Sheets!</div>', unsafe_allow_html=True)

    with tab3:
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)

        with col1:
            st.markdown('<div class="config-section"><h4>THÔNG TIN HỆ THỐNG</h4>', unsafe_allow_html=True)
            branch = st.text_input("Chi nhánh", value=config.get("branch", "HUE"))
            soc_sender = st.text_input("Tên người gửi SOC", value=config.get("soc_sender_name", "SOC Canh bao"))
            st.markdown("</div>", unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="config-section"><h4>LỊCH TRÌNH</h4>', unsafe_allow_html=True)
            sched = config.get("scheduler", {})
            scan_min = st.number_input("Quét mỗi (phút)", 5, 120, sched.get("scan_interval_minutes", 30))
            reply_h = st.number_input("Giờ gửi tự động", 0, 23, sched.get("reply_deadline_hour", 11))
            reply_m = st.number_input("Phút gửi tự động", 0, 59, sched.get("reply_deadline_minute", 45))
            st.markdown("</div>", unsafe_allow_html=True)

        if st.button("💾 Lưu cài đặt hệ thống", type="primary"):
            config["branch"] = branch
            config["soc_sender_name"] = soc_sender
            config["scheduler"] = {"scan_interval_minutes": scan_min, "reply_deadline_hour": reply_h, "reply_deadline_minute": reply_m}
            save_config(config)
            st.markdown('<div class="alert-box success">✅ Đã lưu cài đặt!</div>', unsafe_allow_html=True)

    with tab4:
        st.markdown("<br>", unsafe_allow_html=True)
        email_cfg = config.get("email", {})

        st.markdown('<div class="section-label">KIỂM TRA KẾT NỐI</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔌 Test IMAP", use_container_width=True, disabled=not email_cfg.get("address")):
                with st.spinner("Đang kết nối IMAP..."):
                    from utils.email_utils import test_imap_connection
                    ok, msg = test_imap_connection(email_cfg["address"], email_cfg["password"], email_cfg.get("imap_server", "imap.gmail.com"))
                    cls = "success" if ok else "error"
                    icon = "✅" if ok else "❌"
                    st.markdown(f'<div class="alert-box {cls}">{icon} {msg}</div>', unsafe_allow_html=True)

        with col2:
            if st.button("📤 Test SMTP", use_container_width=True, disabled=not email_cfg.get("address")):
                with st.spinner("Đang kết nối SMTP..."):
                    from utils.email_utils import test_smtp_connection
                    ok, msg = test_smtp_connection(email_cfg["address"], email_cfg["password"], email_cfg.get("smtp_server", "smtp.gmail.com"))
                    cls = "success" if ok else "error"
                    icon = "✅" if ok else "❌"
                    st.markdown(f'<div class="alert-box {cls}">{icon} {msg}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        sheets_cfg = config.get("google_sheets", {})

        if st.button("📊 Test Google Sheets", use_container_width=True, disabled=not sheets_cfg.get("credentials_path")):
            with st.spinner("Đang kết nối Google Sheets..."):
                try:
                    from utils.sheets_utils import get_all_sheets_info
                    tabs = get_all_sheets_info(sheets_cfg["credentials_path"], sheets_cfg.get("spreadsheet_id", ""))
                    st.markdown(f'<div class="alert-box success">✅ Kết nối thành công! Tìm thấy {len(tabs)} tab: {", ".join(tabs)}</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.markdown(f'<div class="alert-box error">❌ Lỗi Sheets: {str(e)}</div>', unsafe_allow_html=True)
