"""Google Sheets viewer page"""
import streamlit as st
import json
from pathlib import Path

STATE_FILE = Path("/home/claude/soc-automation/config/state.json")

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
            <div class="subtitle">Xem và kiểm tra nội dung giải trình theo từng tab chỉ số</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    sheets_cfg = config.get("google_sheets", {})
    spreadsheet_id = sheets_cfg.get("spreadsheet_id", "11A4TuYjE3iLU92IvYK3UlOclB2baOd7Yawd4LyGrsW8")
    creds_path = sheets_cfg.get("credentials_path", "")

    # Sheet link
    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    st.markdown(f"""
    <div class="alert-box info" style="display:flex; align-items:center; justify-content:space-between;">
        <span>📊 Google Sheets: <code style="font-family:var(--mono); font-size:11px;">{spreadsheet_id}</code></span>
        <a href="{sheet_url}" target="_blank" style="color:#90CDF4; font-family:var(--mono); font-size:11px; text-decoration:none; border:1px solid #2B6CB0; padding:4px 12px; border-radius:3px;">Mở Sheet ↗</a>
    </div>
    """, unsafe_allow_html=True)

    state = load_state()
    red_indicators = state.get("red_indicators", [])
    report_date = state.get("report_date", "")

    col1, col2 = st.columns([2, 1])

    with col2:
        st.markdown('<div class="section-label">TUỲ CHỌN</div>', unsafe_allow_html=True)

        if not creds_path:
            st.markdown("""
            <div class="alert-box warning">
                ⚠️ Chưa cấu hình Google Service Account. Vào <strong>Cấu hình → Google Sheets</strong> để thiết lập.
            </div>
            """, unsafe_allow_html=True)
        else:
            from utils.sheets_utils import INDICATOR_TO_SHEET
            all_sheets = list(INDICATOR_TO_SHEET.keys())

            selected_sheets = st.multiselect(
                "Chọn sheet cần xem",
                all_sheets,
                default=red_indicators if red_indicators else []
            )
            filter_date = st.text_input("Lọc theo ngày (dd/mm/yyyy)", value=report_date or "")

            if st.button("🔄 Tải dữ liệu", type="primary", use_container_width=True):
                if selected_sheets:
                    st.session_state.sheets_to_load = selected_sheets
                    st.session_state.sheets_filter_date = filter_date

    with col1:
        st.markdown('<div class="section-label">NỘI DUNG GIẢI TRÌNH</div>', unsafe_allow_html=True)

        if not creds_path:
            # Show iframe embed as fallback
            st.markdown(f"""
            <div style="border:1px solid var(--border); border-radius:4px; overflow:hidden; height:500px;">
                <iframe src="https://docs.google.com/spreadsheets/d/{spreadsheet_id}/htmlembed?widget=true&headers=false"
                    style="width:100%; height:100%; border:none;"
                    sandbox="allow-scripts allow-same-origin allow-popups">
                </iframe>
            </div>
            """, unsafe_allow_html=True)
        else:
            sheets_to_load = st.session_state.get("sheets_to_load", [])
            if not sheets_to_load and red_indicators:
                sheets_to_load = red_indicators

            if sheets_to_load:
                from utils.sheets_utils import collect_all_explanations
                with st.spinner("Đang tải từ Google Sheets..."):
                    try:
                        data = collect_all_explanations(
                            creds_path,
                            spreadsheet_id,
                            sheets_to_load,
                            st.session_state.get("sheets_filter_date", report_date)
                        )
                        st.session_state.sheets_data = data

                        for item in data:
                            if item["error"]:
                                st.markdown(f'<div class="alert-box error">❌ Tab "{item["sheet_name"]}": {item["error"]}</div>', unsafe_allow_html=True)
                            else:
                                status = "green" if item["count"] > 0 else "orange"
                                st.markdown(f"""
                                <div class="status-row" style="margin-bottom:8px;">
                                    <div class="dot {status}"></div>
                                    <strong style="font-size:13px;">{item['indicator']}</strong>
                                    <span style="color:var(--text-muted); font-size:12px; margin-left:8px;">→ Tab: {item['sheet_name']}</span>
                                    <span style="margin-left:auto; font-family:var(--mono); font-size:11px; color:{'#48BB78' if item['count']>0 else '#ED8936'};">{item['count']} dòng</span>
                                </div>
                                """, unsafe_allow_html=True)

                                if item["rows"]:
                                    import pandas as pd
                                    df = pd.DataFrame(item["rows"])
                                    st.dataframe(df, use_container_width=True, hide_index=True)
                                else:
                                    st.markdown(f'<div class="alert-box warning">⚠️ Tab "{item["sheet_name"]}" chưa có dữ liệu giải trình.</div>', unsafe_allow_html=True)

                    except Exception as e:
                        st.markdown(f'<div class="alert-box error">❌ Lỗi kết nối Google Sheets: {str(e)}</div>', unsafe_allow_html=True)
            else:
                if red_indicators:
                    st.markdown('<div class="alert-box info">Nhấn "Tải dữ liệu" để xem nội dung giải trình.</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="alert-box info">Chưa có chỉ số đỏ. Hãy quét email trước.</div>', unsafe_allow_html=True)

    # Sheet mapping reference
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("📌 Bảng ánh xạ Chỉ số → Tab Sheet"):
        from utils.sheets_utils import INDICATOR_TO_SHEET
        import pandas as pd
        df_map = pd.DataFrame([
            {"Chỉ số": k, "Tab Google Sheets": v}
            for k, v in INDICATOR_TO_SHEET.items()
        ])
        st.dataframe(df_map, use_container_width=True, hide_index=True)
