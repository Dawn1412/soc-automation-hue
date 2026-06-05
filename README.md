# SOC Alert Automation – Chi nhánh Huế

Hệ thống tự động hóa quy trình: Nhận email cảnh báo → Quản lý giải trình Google Sheets → Gửi phản hồi tự động.

## Cài đặt

```bash
pip install -r requirements.txt
```

## Chạy ứng dụng

### 1. Web UI (Streamlit)
```bash
streamlit run app.py
```
Truy cập: http://localhost:8501

### 2. Background Scheduler (chạy riêng)
```bash
python scheduler_runner.py
```

## Cấu hình

### Email (Gmail)
1. Bật 2-Factor Authentication trên Gmail
2. Tạo App Password: Tài khoản Google → Bảo mật → Mật khẩu ứng dụng
3. Nhập vào Cài đặt → Email

### Google Sheets
1. Vào Google Cloud Console → Enable Google Sheets API + Drive API
2. Tạo Service Account → Download JSON key
3. Chia sẻ Google Sheet với email của Service Account (Editor)
4. Nhập đường dẫn JSON vào Cài đặt → Google Sheets

## Luồng vận hành

```
SOC Email → [IMAP Scan] → Parse chỉ số đỏ
                              ↓
                    Nhân viên cập nhật Google Sheets
                              ↓
              [APScheduler 11:45] → Đọc Sheets → Build HTML → SMTP Reply
```

## Cấu trúc

```
soc-automation/
├── app.py                  # Streamlit main app
├── scheduler_runner.py     # Background scheduler
├── requirements.txt
├── config/
│   ├── settings.json       # Cấu hình (tự tạo)
│   ├── state.json          # Trạng thái runtime
│   └── logs.json           # Nhật ký
├── pages/
│   ├── dashboard.py
│   ├── email_scan.py
│   ├── sheets_view.py
│   ├── send_email.py
│   ├── scheduler_page.py
│   ├── settings_page.py
│   └── logs_page.py
└── utils/
    ├── email_utils.py      # IMAP/SMTP
    └── sheets_utils.py     # Google Sheets
```
