"""Google Sheets viewer page - Auto refresh"""
import streamlit as st
import json
from pathlib import Path
import time

STATE_FILE = Path(__file__).parent.parent / "config" / "state.json"

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"red_indicators": [], "report_date": None}

def render(config: dict):
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>📋 Google Sheets – Giải trình</h1>
            <div class="subtitle">Dữ liệu tự động cập nhật mỗi 60 giây</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    sheets_cfg = config.get("google_sheets", {})
    spreadsheet_id = sheets_cfg.get("spreadsheet_id", "")
    creds_path = sheets_cfg.get("credentials_path", "")
    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

    # Auto refresh countdown
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        st.markdown(f"""
        <div class="alert-box info" style="display:flex; align-items:center; justify-content:space-between;">
            <span>📊 Google Sheets: <code style="font-family:var(--mono); font-size:11px;">{spreadsheet_id}</code></span>
            <a href="{sheet_url}" target="_blank" style="color:#90CDF4; font-family:var(--mono); font-size:11px; text-decoration:none; border:1px solid #2B6CB0; padding:4px 12px; border-radius:3px;">Mở Sheet ↗</a>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        auto_refresh = st.toggle("🔄 Auto refresh", value=True)
    with col3:
        refresh_interval = st.selectbox("Mỗi", [30, 60, 120, 300], index=1, format_func=lambda x: f"{x}s")

    state = load_state()
    red_indicators = state.get("red_indicators", [])
    report_date = state.get("report_date", "")

    col_main, col_side = st.columns([3, 1])

    with col_side:
        st.markdown('<div class="section-label">CHỌN SHEET</div>', unsafe_allow_html=True)
        from utils.sheets_utils import INDICATOR_TO_SHEET
        all_sheets = list(INDICATOR_TO_SHEET.keys())
        selected_sheets = st.multiselect(
            "Chọn sheet cần xem",
            all_sheets,
            default=red_indicators if red_indicators else [],
            label_visibility="collapsed"
        )
        filter_date = st.text_input("Lọc theo ngày", value=report_date or "", placeholder="dd/mm/yyyy")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Tải ngay", type="primary", use_container_width=True):
            st.session_state.force_refresh = True
            st.rerun()

        # Last updated
        if "last_sheets_update" in st.session_state:
            st.markdown(f"""
            <div style="font-family:var(--mono); font-size:10px; color:var(--text-muted); margin-top:8px; text-align:center;">
                Cập nhật lúc:<br>{st.session_state.last_sheets_update}
            </div>
            """, unsafe_allow_html=True)

    with col_main:
        st.markdown('<div class="section-label">NỘI DUNG GIẢI TRÌNH</div>', unsafe_allow_html=True)

        sheets_to_load = selected_sheets if selected_sheets else red_indicators

        if sheets_to_load:
            # Load data
            with st.spinner("Đang tải dữ liệu mới nhất từ Google Sheets..."):
                try:
                    from utils.sheets_utils import collect_all_explanations
                    data = collect_all_explanations(
                        creds_path,
                        spreadsheet_id,
                        sheets_to_load,
                        filter_date
                    )
                    st.session_state.sheets_data = data
                    st.session_state.last_sheets_update = __import__('datetime').datetime.now().strftime("%H:%M:%S")

                    # Hiển thị từng sheet
                    for item in data:
                        if item["error"]:
                            st.markdown(f'<div class="alert-box error">❌ Tab "{item["sheet_name"]}": {item["error"]}</div>', unsafe_allow_html=True)
                            continue

                        status_color = "green" if item["count"] > 0 else "orange"
                        st.markdown(f"""
                        <div class="status-row" style="margin-bottom:8px;">
                            <div class="dot {status_color}"></div>
                            <strong style="font-size:13px;">{item['indicator']}</strong>
                            <span style="color:var(--text-muted); font-size:12px; margin-left:8px;">→ {item['sheet_name']}</span>
                            <span style="margin-left:auto; font-family:var(--mono); font-size:11px; color:{'#48BB78' if item['count']>0 else '#ED8936'};">{item['count']} dòng</span>
                        </div>
                        """, unsafe_allow_html=True)

                        if item["rows"]:
                            import pandas as pd
                            df = pd.DataFrame(item["rows"])
                            # Bỏ cột Col_x
                            df = df[[c for c in df.columns if not c.startswith("Col_")]]
                            st.dataframe(df, use_container_width=True, hide_index=True)
                        else:
                            st.markdown(f'<div class="alert-box warning">⚠️ Tab "{item["sheet_name"]}" chưa có dữ liệu.</div>', unsafe_allow_html=True)

                        st.markdown("<br>", unsafe_allow_html=True)

                except Exception as e:
                    st.markdown(f'<div class="alert-box error">❌ Lỗi: {str(e)}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="alert-box info">Chọn sheet bên phải để xem dữ liệu giải trình.</div>', unsafe_allow_html=True)

    # Auto refresh
    if auto_refresh and sheets_to_load:
        time.sleep(refresh_interval)
        st.rerun()