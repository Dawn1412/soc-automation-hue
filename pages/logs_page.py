"""Logs page"""
import streamlit as st
import json
from pathlib import Path
from datetime import datetime

LOG_FILE = Path(__file__).parent.parent / "config" / "logs.json"

def render():
    st.markdown("""
    <div class="sys-header">
        <div>
            <h1>📜 Nhật ký Hoạt động</h1>
            <div class="subtitle">Lịch sử quét email, tổng hợp và gửi báo cáo</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    logs = []
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            logs = json.load(f)

    col1, col2 = st.columns([3, 1])

    with col2:
        st.markdown('<div class="section-label">LỌC NHẬT KÝ</div>', unsafe_allow_html=True)
        action_filter = st.selectbox("Loại hành động", ["Tất cả", "EMAIL_SENT", "SCAN_EMAIL", "ERROR"])
        status_filter = st.selectbox("Trạng thái", ["Tất cả", "success", "error", "warning"])

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ Xoá nhật ký", use_container_width=True):
            with open(LOG_FILE, "w") as f:
                json.dump([], f)
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # Stats
        total = len(logs)
        success_count = len([l for l in logs if l.get("status") == "success"])
        error_count = len([l for l in logs if l.get("status") == "error"])

        st.markdown(f"""
        <div class="metric-card blue" style="padding:14px; margin-bottom:8px;">
            <div class="label">Tổng log</div>
            <div class="value">{total}</div>
        </div>
        <div class="metric-card green" style="padding:14px; margin-bottom:8px;">
            <div class="label">Thành công</div>
            <div class="value">{success_count}</div>
        </div>
        <div class="metric-card red" style="padding:14px; margin-bottom:8px;">
            <div class="label">Lỗi</div>
            <div class="value">{error_count}</div>
        </div>
        """, unsafe_allow_html=True)

    with col1:
        st.markdown('<div class="section-label">NHẬT KÝ GẦN ĐÂY</div>', unsafe_allow_html=True)

        # Filter
        filtered = logs
        if action_filter != "Tất cả":
            filtered = [l for l in filtered if l.get("action") == action_filter]
        if status_filter != "Tất cả":
            filtered = [l for l in filtered if l.get("status") == status_filter]

        if not filtered:
            st.markdown('<div class="alert-box info">Không có nhật ký nào phù hợp với bộ lọc.</div>', unsafe_allow_html=True)
            
            # Add demo log
            if st.button("➕ Thêm log demo"):
                demo_logs = [
                    {"time": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "action": "SCAN_EMAIL", "detail": "Quét email từ SOC Canh bao – Tìm thấy 2 email", "status": "success"},
                    {"time": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "action": "EMAIL_SENT", "detail": "Gửi đến soccanh@fpt.com – 3 chỉ số đỏ", "status": "success"},
                ]
                LOG_FILE.parent.mkdir(exist_ok=True)
                with open(LOG_FILE, "w") as f:
                    json.dump(demo_logs, f, ensure_ascii=False, indent=2)
                st.rerun()
        else:
            for log in filtered:
                status = log.get("status", "info")
                color = "green" if status == "success" else ("red" if status == "error" else "orange")
                icon = "✅" if status == "success" else ("❌" if status == "error" else "⚠️")

                st.markdown(f"""
                <div class="timeline-item">
                    <div class="timeline-time">{log.get('time','')}</div>
                    <div class="timeline-content">
                        <div class="timeline-title">
                            {icon} {log.get('action','')}
                        </div>
                        <div class="timeline-desc">{log.get('detail','')}</div>
                    </div>
                    <div class="dot {color}" style="margin-top:6px; flex-shrink:0;"></div>
                </div>
                """, unsafe_allow_html=True)

            # Export
            st.markdown("<br>", unsafe_allow_html=True)
            import pandas as pd
            df = pd.DataFrame(filtered)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Xuất CSV",
                data=csv,
                file_name=f"soc_logs_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
