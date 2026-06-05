"""
Google Sheets utilities using gspread + service account or OAuth2
"""
import json
from typing import Optional
import re

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
    "Checklist lặp ≥ 3": "Checklist lặp",
    "PTC ≥ 72h": "PTC",
    "Checklist ≥24h": "Checklist 24h",
    "Yêu Cầu RM": "Yêu Cầu RM",
    "Yêu cầu khiếu nại": "Khiếu nại",
    "Yêu cầu ≥48h": "YC 48h",
}


def get_gspread_client(credentials_path: str):
    """Create gspread client from service account JSON file."""
    if not GSPREAD_AVAILABLE:
        raise ImportError("gspread not installed. Run: pip install gspread google-auth")
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)


def get_sheet_data(credentials_path: str, spreadsheet_id: str, sheet_name: str) -> list[dict]:
    """Fetch all records from a specific sheet tab."""
    client = get_gspread_client(credentials_path)
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(sheet_name)
    records = ws.get_all_records()
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
    """Build HTML email body from collected explanations."""
    rows_html = ""
    for exp in explanations:
        status = "✅" if exp["count"] > 0 else "⚠️"
        rows_html += f"""
        <tr>
            <td style="padding:10px 14px; border-bottom:1px solid #e2e8f0; font-weight:600; color:#c53030;">{exp['indicator']}</td>
            <td style="padding:10px 14px; border-bottom:1px solid #e2e8f0;">{exp['sheet_name']}</td>
            <td style="padding:10px 14px; border-bottom:1px solid #e2e8f0; text-align:center;">{exp['count']} dòng</td>
            <td style="padding:10px 14px; border-bottom:1px solid #e2e8f0; text-align:center;">{status}</td>
        </tr>
        """

    detail_html = ""
    for exp in explanations:
        if exp["rows"]:
            detail_html += f"<h3 style='color:#c53030; margin:24px 0 10px;'>📋 {exp['indicator']}</h3>"
            # Build mini table
            if exp["rows"]:
                headers = list(exp["rows"][0].keys())
                th_html = "".join(f"<th style='padding:8px 12px; text-align:left; background:#f7fafc; border:1px solid #e2e8f0;'>{h}</th>" for h in headers)
                td_rows = ""
                for row in exp["rows"][:20]:  # max 20 rows
                    tds = "".join(f"<td style='padding:8px 12px; border:1px solid #e2e8f0;'>{v}</td>" for v in row.values())
                    td_rows += f"<tr>{tds}</tr>"
                detail_html += f"""
                <table style="border-collapse:collapse; width:100%; font-size:13px; margin-bottom:16px;">
                    <thead><tr>{th_html}</tr></thead>
                    <tbody>{td_rows}</tbody>
                </table>"""
        else:
            detail_html += f"<p style='color:#718096;'>⚠️ Chưa có giải trình cho: <strong>{exp['indicator']}</strong></p>"

    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width:800px; color:#2d3748;">
        <div style="background:#c53030; color:white; padding:20px 28px; border-radius:6px 6px 0 0;">
            <h2 style="margin:0; font-size:1.3rem;">📊 Báo cáo Giải trình Chỉ số Đỏ</h2>
            <p style="margin:6px 0 0; opacity:0.85; font-size:0.9rem;">Chi nhánh {branch} – Ngày báo cáo: {report_date}</p>
        </div>
        <div style="background:#fff8f8; border:1px solid #fed7d7; border-top:none; padding:20px 28px; border-radius:0 0 6px 6px;">
            <p>Kính gửi SOC Canh Bao,</p>
            <p>Chi nhánh <strong>{branch}</strong> xin gửi giải trình về các chỉ số đỏ trong ngày <strong>{report_date}</strong> như sau:</p>

            <table style="width:100%; border-collapse:collapse; margin:16px 0; font-size:13px;">
                <thead>
                    <tr style="background:#fff5f5;">
                        <th style="padding:10px 14px; text-align:left; border-bottom:2px solid #c53030; color:#c53030;">Chỉ số</th>
                        <th style="padding:10px 14px; text-align:left; border-bottom:2px solid #c53030; color:#c53030;">Tab Sheet</th>
                        <th style="padding:10px 14px; text-align:center; border-bottom:2px solid #c53030; color:#c53030;">Số dòng GS</th>
                        <th style="padding:10px 14px; text-align:center; border-bottom:2px solid #c53030; color:#c53030;">Trạng thái</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>

            <hr style="border:none; border-top:1px solid #fed7d7; margin:24px 0;" />
            <h3 style="color:#2d3748; margin-bottom:12px;">Chi tiết giải trình:</h3>
            {detail_html}

            <hr style="border:none; border-top:1px solid #fed7d7; margin:24px 0;" />
            <p style="color:#718096; font-size:12px;">
                Email này được tạo tự động bởi hệ thống SOC Automation – Chi nhánh {branch}.<br>
                Thời gian gửi: {__import__('datetime').datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            </p>
        </div>
    </div>
    """
    return html
