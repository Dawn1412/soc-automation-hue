"""
Email Scan page
- Luôn lấy email SOC MỚI NHẤT (sort theo Date header)
- Hiển thị rõ ngày nhận, deadline, chỉ số đỏ
- Lưu report_date chính xác vào state để sheets_utils lọc đúng
"""
import streamlit as st
import json
from pathlib import Path
from datetime import datetime

STATE_FILE = Path(__file__).parent.parent / "config" / "state.json"


def save_state(state: dict):
    STATE_FILE.parent.mkdir(exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_scan": None, "red_indicators": [], "report_date": None,
        "deadline": None, "status": "idle", "total_scans": 0,
        "total_emails_sent": 0, "last_email_sent": None,
    }


def render(config: dict):
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>📧 Quét Email SOC</h1>
            <div class="subtitle">Tự động lấy email cảnh báo MỚI NHẤT từ SOC Canh Bao</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    email_cfg  = config.get("email", {})
    has_config = bool(email_cfg.get("address") and email_cfg.get("password"))

    if not has_config:
        st.markdown("""
        <div class="alert-box warning">
            ⚠️ Chưa cấu hình email. Vui lòng vào <strong>Cấu hình</strong> trước.
        </div>
        """, unsafe_allow_html=True)
        if st.button("⚙️ Đi đến Cấu hình"):
            st.session_state.page = "settings"
            st.rerun()
        return

    col1, col2 = st.columns([2, 1])

    # ── Cột phải: tuỳ chọn quét ──
    with col2:
        st.markdown('<div class="section-label">CẤU HÌNH QUÉT</div>', unsafe_allow_html=True)
        sender_name = st.text_input(
            "Tên người gửi SOC",
            value=config.get("soc_sender_name", "SOC Canh bao")
        )
        limit = st.number_input("Số email tối đa tìm kiếm", min_value=1, max_value=50, value=10)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔍 Quét & Lấy Email Mới Nhất", type="primary", use_container_width=True):
            st.session_state.trigger_scan    = True
            st.session_state.scan_sender     = sender_name
            st.session_state.scan_limit      = limit

        # Hiển thị trạng thái state hiện tại
        st.markdown("<br>", unsafe_allow_html=True)
        state = load_state()
        if state.get("last_scan"):
            st.markdown(f"""
            <div class="config-section" style="padding:14px;">
                <h4>TRẠNG THÁI HIỆN TẠI</h4>
                <div style="font-size:12px; line-height:2; color:var(--text-muted);">
                    <div>🕐 Quét lúc: <span style="color:var(--text);">{state['last_scan']}</span></div>
                    <div>📅 Ngày BC: <span style="color:var(--text);">{state.get('report_date') or '—'}</span></div>
                    <div>⏰ Deadline: <span style="color:var(--red);">{state.get('deadline') or '—'}</span></div>
                    <div>🔴 Chỉ số đỏ: <span style="color:var(--red); font-weight:600;">{len(state.get('red_indicators', []))}</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ── Cột trái: kết quả ──
    with col1:
        st.markdown('<div class="section-label">KẾT QUẢ QUÉT</div>', unsafe_allow_html=True)

        if st.session_state.get("trigger_scan"):
            st.session_state.trigger_scan = False
            with st.spinner("Đang kết nối IMAP và lấy email mới nhất..."):
                try:
                    from utils.email_utils import connect_imap, search_soc_emails, parse_soc_email

                    mail   = connect_imap(
                        email_cfg["address"],
                        email_cfg["password"],
                        email_cfg.get("imap_server", "imap.gmail.com")
                    )
                    emails = search_soc_emails(
                        mail,
                        st.session_state.scan_sender,
                        st.session_state.scan_limit
                    )
                    mail.logout()

                    if not emails:
                        st.markdown(
                            f'<div class="alert-box warning">'
                            f'Không tìm thấy email nào từ "{st.session_state.scan_sender}".'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        # emails[0] đã là MỚI NHẤT (đã sort trong search_soc_emails)
                        latest = emails[0]
                        parsed = parse_soc_email(latest["body"], latest["date"])

                        st.session_state.scanned_emails = emails
                        st.session_state.parsed_email   = parsed

                        # ── Lưu state ──
                        state = load_state()
                        state["last_scan"]             = datetime.now().strftime("%d/%m/%Y %H:%M")
                        state["total_scans"]           = state.get("total_scans", 0) + 1
                        state["red_indicators"]        = parsed["red_indicators"]
                        state["report_date"]           = parsed["report_date"]
                        state["deadline"]              = parsed["deadline"]
                        state["status"]                = "active"
                        state["latest_email_sender"]   = latest["sender"]
                        state["latest_email_subject"]  = latest["subject"]
                        state["latest_email_date"]     = latest["date"]   # raw header
                        save_state(state)

                        # Hiển thị thông tin email mới nhất
                        received_dt = latest.get("parsed_dt")
                        received_str = (
                            received_dt.strftime("%d/%m/%Y %H:%M")
                            if received_dt else latest["date"]
                        )
                        st.markdown(f"""
                        <div class="alert-box success">
                            ✅ Tìm thấy <strong>{len(emails)}</strong> email.
                            Đang dùng email <strong>MỚI NHẤT</strong>
                            nhận lúc <strong>{received_str}</strong>.
                        </div>
                        """, unsafe_allow_html=True)

                except Exception as e:
                    st.markdown(
                        f'<div class="alert-box error">❌ Lỗi kết nối: {str(e)}</div>',
                        unsafe_allow_html=True
                    )

        # ── Hiển thị kết quả parse ──
        if st.session_state.get("parsed_email"):
            parsed = st.session_state.parsed_email
            emails = st.session_state.get("scanned_emails", [])

            if emails:
                latest       = emails[0]
                received_dt  = latest.get("parsed_dt")
                received_str = (
                    received_dt.strftime("%d/%m/%Y %H:%M")
                    if received_dt else latest["date"]
                )

                st.markdown(f"""
                <div class="config-section" style="margin-bottom:16px;">
                    <h4>EMAIL MỚI NHẤT ĐÃ CHỌN</h4>
                    <div style="font-size:13px; line-height:2;">
                        <div>
                            <span style="color:var(--text-muted); font-family:var(--mono); font-size:11px;">TỪ:</span>
                            {latest['sender']}
                        </div>
                        <div>
                            <span style="color:var(--text-muted); font-family:var(--mono); font-size:11px;">CHỦ ĐỀ:</span>
                            {latest['subject']}
                        </div>
                        <div>
                            <span style="color:var(--text-muted); font-family:var(--mono); font-size:11px;">NHẬN LÚC:</span>
                            <strong style="color:#48BB78;">{received_str}</strong>
                            &nbsp;
                            <span style="font-family:var(--mono); font-size:10px; background:rgba(72,187,120,0.15);
                                color:#48BB78; padding:2px 8px; border-radius:10px;">MỚI NHẤT</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Nếu có nhiều email, hiển thị danh sách để tham khảo
                if len(emails) > 1:
                    with st.expander(f"📋 Xem tất cả {len(emails)} email tìm được"):
                        for i, em in enumerate(emails):
                            dt   = em.get("parsed_dt")
                            dstr = dt.strftime("%d/%m/%Y %H:%M") if dt else em["date"]
                            tag  = " 🟢 MỚI NHẤT" if i == 0 else ""
                            st.markdown(f"""
                            <div class="status-row" style="font-size:12px;">
                                <div class="dot {'green' if i == 0 else 'gray'}"></div>
                                <div>
                                    <div style="font-weight:{'600' if i==0 else '400'};">{em['subject']}{tag}</div>
                                    <div style="color:var(--text-muted); font-size:11px;">{dstr}</div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

            # ── KPI metrics ──
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"""
                <div class="metric-card orange" style="padding:14px;">
                    <div class="label">Ngày báo cáo</div>
                    <div style="font-size:1rem; font-weight:700; color:#ED8936; margin-top:4px;">
                        {parsed.get('report_date') or 'Không xác định'}
                    </div>
                </div>""", unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div class="metric-card red" style="padding:14px;">
                    <div class="label">Deadline phản hồi</div>
                    <div style="font-size:1rem; font-weight:700; color:var(--red); margin-top:4px;">
                        {parsed.get('deadline') or '12:00 hôm sau'}
                    </div>
                </div>""", unsafe_allow_html=True)
            with c3:
                st.markdown(f"""
                <div class="metric-card red" style="padding:14px;">
                    <div class="label">Chỉ số đỏ</div>
                    <div class="value">{len(parsed.get('red_indicators', []))}</div>
                </div>""", unsafe_allow_html=True)

            # ── Chỉ số đỏ ──
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<div class="section-label">CHỈ SỐ ĐỎ ĐÃ NHẬN DIỆN</div>', unsafe_allow_html=True)

            red_inds = parsed.get("red_indicators", [])
            if red_inds:
                for ind in red_inds:
                    st.markdown(f"""
                    <div class="status-row">
                        <div class="dot red"></div>
                        <span style="font-size:13px; font-weight:500;">{ind}</span>
                        <span style="margin-left:auto; font-family:var(--mono); font-size:10px;
                            color:var(--text-muted);">CẦN GIẢI TRÌNH</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div class="alert-box info">'
                    'Chưa nhận diện được chỉ số đỏ tự động. Thêm thủ công bên dưới.</div>',
                    unsafe_allow_html=True
                )

            # ── Thêm thủ công ──
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("➕ Thêm / chỉnh sửa chỉ số đỏ thủ công"):
                from utils.sheets_utils import INDICATOR_TO_SHEET
                all_indicators  = list(INDICATOR_TO_SHEET.keys())
                safe_default    = [x for x in red_inds if x in all_indicators]
                selected        = st.multiselect("Chọn chỉ số đỏ", all_indicators, default=safe_default)
                if st.button("💾 Cập nhật danh sách", type="primary"):
                    state = load_state()
                    state["red_indicators"] = selected
                    save_state(state)
                    st.session_state.parsed_email["red_indicators"] = selected
                    st.success("Đã cập nhật!")
                    st.rerun()

            # ── Body gốc ──
            with st.expander("📄 Xem nội dung email gốc"):
                if emails:
                    st.text_area("Nội dung", value=emails[0]["body"], height=300, disabled=True)

        elif not st.session_state.get("trigger_scan"):
            state = load_state()
            if state.get("last_scan"):
                st.markdown(f"""
                <div class="alert-box info">
                    🕐 Lần quét cuối: <strong>{state['last_scan']}</strong><br>
                    📅 Ngày báo cáo: <strong>{state.get('report_date') or '—'}</strong><br>
                    🔴 Chỉ số đỏ: <strong>{', '.join(state.get('red_indicators', [])) or 'Không có'}</strong>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div class="alert-box info">Nhấn "Quét & Lấy Email Mới Nhất" để bắt đầu.</div>',
                    unsafe_allow_html=True
                )