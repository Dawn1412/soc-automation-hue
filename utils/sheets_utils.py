"""
Google Sheets utilities using gspread + service account or OAuth2
"""
import json
from typing import Optional
import re
from pathlib import Path

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

SPREADSHEET_ID = "11A4TuYjE3iLU92IvYK3UlOclB2baOd7Yawd4LyGrsW8"

# Mapping from indicator name -> sheet tab name
INDICATOR_TO_SHEET = {
    "CSAT 1": "CSAT 1",
    "Checklist lặp ≥ 3": "Checklist lặp ≥ 3",
    "PTC ≥ 72h": "PTC ≥ 72h",
    "Checklist ≥24h": "Checklist ≥24h",
    "Yêu Cầu RM": "Suy hao cao yêu cầu huỷ",
    "Nguyên nhân tồn TKM": "Nguyên nhân tồn TKM",
    "Rời mạng CLDV": "Rời mạng CLDV",
}


def get_gspread_client(credentials_path: str = None):
    """Create gspread client from Streamlit Secrets or service account JSON file."""
    if not GSPREAD_AVAILABLE:
        raise ImportError("gspread not installed.")
    
    # Thử đọc từ Streamlit Secrets trước
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'google_service_account' in st.secrets:
            creds = Credentials.from_service_account_info(
                dict(st.secrets["google_service_account"]),
                scopes=SCOPES
            )
            return gspread.authorize(creds)
    except Exception:
        pass
    
    # Fallback: đọc từ file JSON (local)
    if credentials_path and Path(credentials_path).exists():
        creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        return gspread.authorize(creds)
    
    raise ValueError("Không tìm thấy thông tin xác thực Google!")


def get_sheet_data(credentials_path: str, spreadsheet_id: str, sheet_name: str) -> list[dict]:
    """Fetch all records from a specific sheet tab."""
    client = get_gspread_client(credentials_path)
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(sheet_name)
    # Dung expected_headers de tranh loi duplicate
    data = ws.get_all_values()
    if not data:
        return []
    headers = []
    seen = {}
    for i, h in enumerate(data[0]):
        h = h.strip() if h.strip() else f"Col_{i}"
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
        headers.append(h)
    records = []
    for row in data[1:]:
        if any(cell.strip() for cell in row):
            records.append(dict(zip(headers, row)))
    return records


def get_all_sheets_info(credentials_path: str, spreadsheet_id: str) -> list[str]:
    """Get list of all sheet/tab names in the spreadsheet."""
    client = get_gspread_client(credentials_path)
    sh = client.open_by_key(spreadsheet_id)
    return [ws.title for ws in sh.worksheets()]


def extract_explanation_from_sheet(
    credentials_path: str,
    spreadsheet_id: str,
    indicator: str,
    report_date: str = None,
) -> dict:
    """
    Extract explanation/giải trình data from a specific sheet for a given indicator.
    Returns dict with: sheet_name, rows, summary
    """
    sheet_name = INDICATOR_TO_SHEET.get(indicator, indicator)
    try:
        records = get_sheet_data(credentials_path, spreadsheet_id, sheet_name)
        # Filter by date if provided
        if report_date and records:
            date_filtered = []
            for row in records:
                for val in row.values():
                    if report_date in str(val):
                        date_filtered.append(row)
                        break
            if date_filtered:
                records = date_filtered
        return {
            "sheet_name": sheet_name,
            "indicator": indicator,
            "rows": records,
            "count": len(records),
            "error": None,
        }
    except Exception as e:
        return {
            "sheet_name": sheet_name,
            "indicator": indicator,
            "rows": [],
            "count": 0,
            "error": str(e),
        }


def collect_all_explanations(
    credentials_path: str,
    spreadsheet_id: str,
    red_indicators: list[str],
    report_date: str = None,
) -> list[dict]:
    """Collect explanations for all red indicators."""
    results = []
    for indicator in red_indicators:
        data = extract_explanation_from_sheet(credentials_path, spreadsheet_id, indicator, report_date)
        results.append(data)
    return results


def build_email_html(
    report_date: str,
    branch: str,
    explanations: list[dict],
    original_body: str = "",
) -> str:
    rows_html = ""
    for exp in explanations:
        status_icon = "✅" if exp["count"] > 0 else "⚠️"
        status_color = "#27AE60" if exp["count"] > 0 else "#E67E22"
        rows_html += f"""
        <tr>
            <td style="padding:12px 16px; border-bottom:1px solid #F0F0F0;">
                <span style="display:inline-block; width:8px; height:8px; background:#E53935; border-radius:50%; margin-right:8px;"></span>
                <strong style="color:#C62828;">{exp['indicator']}</strong>
            </td>
            <td style="padding:12px 16px; border-bottom:1px solid #F0F0F0; color:#555;">{exp['sheet_name']}</td>
            <td style="padding:12px 16px; border-bottom:1px solid #F0F0F0; text-align:center;">
                <span style="background:#EEF2FF; color:#3949AB; padding:3px 10px; border-radius:12px; font-size:12px; font-weight:600;">{exp['count']} dòng</span>
            </td>
            <td style="padding:12px 16px; border-bottom:1px solid #F0F0F0; text-align:center; color:{status_color}; font-size:16px;">{status_icon}</td>
        </tr>"""

    detail_html = ""
    for exp in explanations:
        if exp.get("rows"):
            headers = list(exp["rows"][0].keys())
            # Lấy TẤT CẢ cột có tên thật (bỏ Col_x)
            real_headers = [h for h in headers if not h.startswith("Col_")]
            if not real_headers:
                 real_headers = headers

            th_html = "".join(
                f'<th style="padding:10px 14px; text-align:left; background:#C62828; color:white; font-size:12px; font-weight:600; white-space:nowrap;">{h}</th>'
                for h in real_headers
            )
            td_rows = ""
            for i, row in enumerate(exp["rows"][:20]):
                bg = "#FFF9F9" if i % 2 == 0 else "#FFFFFF"
                tds = "".join(
                    f'<td style="padding:10px 14px; border-bottom:1px solid #F5E6E6; font-size:12px; color:#333; word-wrap:break-word; max-width:250px;">{str(row.get(h,""))}</td>'
                    for h in real_headers
                )
                td_rows += f'<tr style="background:{bg};">{tds}</tr>'

            detail_html += f"""
            <div style="margin-bottom:28px;">
                <div style="display:flex; align-items:center; margin-bottom:12px;">
                    <div style="width:4px; height:20px; background:#C62828; border-radius:2px; margin-right:10px;"></div>
                    <h3 style="margin:0; font-size:15px; color:#C62828; font-weight:700;">{exp['indicator']}</h3>
                    <span style="margin-left:auto; background:#EEF2FF; color:#3949AB; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600;">{exp['count']} bản ghi</span>
                </div>
                <div style="overflow-x:auto; border-radius:8px; border:1px solid #F5E6E6;">
                    <table style="border-collapse:collapse; width:100%; min-width:400px;">
                        <thead><tr>{th_html}</tr></thead>
                        <tbody>{td_rows}</tbody>
                    </table>
                </div>
            </div>"""
        else:
            detail_html += f"""
            <div style="margin-bottom:20px; padding:14px 18px; background:#FFF8E1; border-left:4px solid #FFC107; border-radius:4px;">
                <span style="color:#F57F17; font-size:13px;">⚠️ Chưa có dữ liệu giải trình cho: <strong>{exp['indicator']}</strong></span>
            </div>"""

    total_records = sum(e["count"] for e in explanations)
    filled = sum(1 for e in explanations if e["count"] > 0)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:0; background:#F4F6F9; font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:680px; margin:24px auto; background:white; border-radius:12px; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.08);">

  <!-- HEADER -->
  <div style="background:linear-gradient(135deg, #C62828 0%, #8B0000 100%); padding:28px 32px;">
    <div style="display:flex; align-items:center; margin-bottom:8px;">
      <div style="width:40px; height:40px; background:rgba(255,255,255,0.2); border-radius:8px; display:flex; align-items:center; justify-content:center; margin-right:14px; font-size:20px;">📊</div>
      <div>
        <h1 style="margin:0; color:white; font-size:20px; font-weight:700; letter-spacing:-0.3px;">Báo cáo Giải trình Chỉ số Đỏ</h1>
        <p style="margin:4px 0 0; color:rgba(255,255,255,0.75); font-size:13px;">Chi nhánh {branch} &nbsp;·&nbsp; Ngày báo cáo: {report_date}</p>
      </div>
    </div>
  </div>

  <!-- STATS BAR -->
  <div style="background:#FFF5F5; padding:16px 32px; border-bottom:1px solid #F5E6E6; display:flex; gap:24px;">
    <div style="text-align:center;">
      <div style="font-size:22px; font-weight:700; color:#C62828;">{len(explanations)}</div>
      <div style="font-size:11px; color:#888; text-transform:uppercase; letter-spacing:0.5px;">Chỉ số đỏ</div>
    </div>
    <div style="width:1px; background:#F5E6E6;"></div>
    <div style="text-align:center;">
      <div style="font-size:22px; font-weight:700; color:#27AE60;">{filled}</div>
      <div style="font-size:11px; color:#888; text-transform:uppercase; letter-spacing:0.5px;">Đã giải trình</div>
    </div>
    <div style="width:1px; background:#F5E6E6;"></div>
    <div style="text-align:center;">
      <div style="font-size:22px; font-weight:700; color:#3949AB;">{total_records}</div>
      <div style="font-size:11px; color:#888; text-transform:uppercase; letter-spacing:0.5px;">Tổng bản ghi</div>
    </div>
  </div>

  <!-- BODY -->
  <div style="padding:28px 32px;">
    <p style="margin:0 0 20px; color:#444; font-size:14px; line-height:1.6;">
      Kính gửi <strong>SOC Canh Bao</strong>,<br>
      Chi nhánh <strong>{branch}</strong> xin gửi giải trình về các chỉ số đỏ trong ngày <strong>{report_date}</strong>:
    </p>

    <!-- SUMMARY TABLE -->
    <div style="border-radius:10px; overflow:hidden; border:1px solid #F5E6E6; margin-bottom:28px;">
      <table style="border-collapse:collapse; width:100%;">
        <thead>
          <tr style="background:#FFF5F5;">
            <th style="padding:12px 16px; text-align:left; font-size:12px; color:#888; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; border-bottom:2px solid #F5E6E6;">Chỉ số</th>
            <th style="padding:12px 16px; text-align:left; font-size:12px; color:#888; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; border-bottom:2px solid #F5E6E6;">Tab Sheet</th>
            <th style="padding:12px 16px; text-align:center; font-size:12px; color:#888; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; border-bottom:2px solid #F5E6E6;">Số dòng</th>
            <th style="padding:12px 16px; text-align:center; font-size:12px; color:#888; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; border-bottom:2px solid #F5E6E6;">Trạng thái</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>

    <!-- DIVIDER -->
    <div style="border-top:2px dashed #F5E6E6; margin:24px 0;"></div>
    <h2 style="margin:0 0 20px; font-size:16px; color:#333; font-weight:700;">📋 Chi tiết giải trình</h2>

    {detail_html}
  </div>

  <!-- FOOTER -->
  <div style="background:#F9FAFB; padding:16px 32px; border-top:1px solid #EEEEEE; text-align:center;">
    <p style="margin:0; font-size:11px; color:#AAAAAA;">
      Email tự động · SOC Automation · Chi nhánh {branch} · {__import__('datetime').datetime.now().strftime('%d/%m/%Y %H:%M')}
    </p>
  </div>

</div>
</body>
</html>"""
    return html 
