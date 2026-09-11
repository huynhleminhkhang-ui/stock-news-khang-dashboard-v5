# 📈 Stock News & Bond Analytics — V5 Alerts Edition

Bản này nâng cấp trực tiếp từ **V4 THEME FIXED**. Hai chức năng cũ vẫn giữ nguyên:

1. **📰 Stock News** — quét tin theo mã, tóm tắt, sentiment, loại tin, trích thông tin trái phiếu, mở bài gốc, xuất CSV.
2. **💵 Bond Valuation** — giá lý thuyết, YTM, Premium/Par/Discount, Macaulay Duration, Modified Duration, bảng cash flow, xuất CSV.

V5 bổ sung tab **🔔 Alerts & Urgency** và pipeline nền:

- GitHub Actions quét tin **mỗi 20 phút**.
- Tin được chấm **Urgency 0–100**.
- Chỉ tin đạt ngưỡng của từng người dùng mới vào Market Digest.
- Gmail Digest gửi ở **07:00, 09:00, 12:00, 17:00 — Asia/Ho_Chi_Minh**.
- Chống gửi trùng **theo từng email nhận** bằng bảng `article_deliveries`.
- Streamlit và GitHub Actions dùng chung **Supabase**, nên web không cần mở liên tục.

---

## 1. Cấu trúc project

```text
.
├── app.py                         # V4 UI + tab Alerts & Urgency
├── urgency.py                     # Urgency engine
├── storage.py                     # Supabase / SQLite fallback
├── background_news.py             # Scanner chạy nền
├── email_service.py               # HTML Gmail Digest
├── supabase_schema.sql            # Database schema
├── jobs/
│   ├── update_news.py
│   └── send_digest.py
├── .github/workflows/
│   ├── update_news.yml            # */20 phút
│   └── send_digest.yml            # 07, 09, 12, 17 giờ
├── .streamlit/config.toml
├── requirements.txt
├── .env.example
└── START_HERE_WINDOWS.bat
```

---

## 2. Chạy local như V4

### Windows
Double-click:

```text
START_HERE_WINDOWS.bat
```

Nếu chưa cấu hình Supabase, tab Alerts dùng **SQLite local** để bạn xem và test giao diện. Hai tab V4 vẫn chạy bình thường.

---

## 3. Tạo Supabase cho V5

1. Tạo một project trên Supabase.
2. Mở **SQL Editor**.
3. Copy toàn bộ nội dung file `supabase_schema.sql` → Run.
4. Lấy:
   - Project URL → `SUPABASE_URL`
   - **service_role key** → `SUPABASE_KEY`

> `service_role` chỉ được đặt trong Streamlit Secrets / GitHub Secrets. Không ghi trực tiếp vào code hoặc commit lên GitHub.

Database có 3 bảng:

- `articles`: tin, ticker, summary, urgency, impact, trạng thái email.
- `subscribers`: Gmail người dùng + ngưỡng urgency.
- `article_deliveries`: lịch sử bài nào đã gửi cho email nào → chống gửi trùng theo user.

---

## 4. Cấu hình Gmail gửi tin

Prototype V5 dùng Gmail SMTP + App Password.

1. Bật **2-Step Verification** cho Gmail gửi.
2. Tạo **App Password**.
3. Lưu 2 secret:

```text
GMAIL_USER
GMAIL_APP_PASSWORD
```

Không dùng mật khẩu Gmail chính.

---

## 5. GitHub Secrets

Repo GitHub → **Settings → Secrets and variables → Actions → Secrets**.

Tạo:

```text
SUPABASE_URL
SUPABASE_KEY
GMAIL_USER
GMAIL_APP_PASSWORD
```

Nếu đang dùng AI summary của V4, `OPENAI_API_KEY` vẫn cấu hình cho Streamlit như trước; pipeline alert hiện không bắt buộc AI nên tiết kiệm chi phí.

---

## 6. GitHub Variables

Repo → **Settings → Secrets and variables → Actions → Variables**.

Khuyến nghị tạo:

```text
WATCH_TICKERS = FPT,TCB,VIC,VHM,PVS,SSI,VCB,BID,CTG,MBB,VPB,HPG,MWG,VNM,GAS
```

Tuỳ chọn:

```text
ALERT_RECIPIENTS = your.receiver@gmail.com
```

`ALERT_RECIPIENTS` chỉ là fallback. Cách đẹp hơn là vào tab **Alerts & Urgency** trên web và đăng ký Gmail tại đó.

---

## 7. Streamlit Cloud Secrets

Trong app Streamlit → **Settings → Secrets**, thêm:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "YOUR_SERVICE_ROLE_KEY"

# Optional V4 deep AI summary
OPENAI_API_KEY = "..."
OPENAI_MODEL = "gpt-5.6-luna"
```

Gmail sender không bắt buộc đặt trong Streamlit nếu việc gửi chỉ chạy bằng GitHub Actions.

---

## 8. Bật workflow lần đầu

GitHub repo → **Actions**.

### A. Update Financial News
Chọn → **Run workflow** một lần.

Workflow sẽ:

```text
Google News RSS
→ merge bài trùng
→ detect tickers
→ Urgency Engine
→ Impact / Scope / Reasons
→ Supabase
```

Sau đó tự chạy mỗi **20 phút**.

### B. Send Market Urgency Digest
Chọn → **Run workflow** để test Gmail.

Sau đó tự chạy:

```text
07:00
09:00
12:00
17:00
```

Timezone: `Asia/Ho_Chi_Minh`.

Nếu không có bài mới đạt ngưỡng → **không gửi email rỗng**.

---

## 9. Urgency Engine

Mặc định:

| Score | Level | Email |
|---:|---|---|
| 90–100 | 🔴 CRITICAL | Có |
| 70–89 | 🟠 HIGH | Có nếu threshold = 70 |
| 45–69 | 🟡 MEDIUM | Dashboard |
| 0–44 | 🟢 LOW | Dashboard |

Engine xét nhiều yếu tố thay vì chỉ một keyword:

- Sự kiện pháp lý: khởi tố, bắt tạm giam, đình chỉ giao dịch, hủy niêm yết…
- Default / trái phiếu: vỡ nợ, chậm thanh toán, gia hạn…
- NHNN / Fed / FOMC / lãi suất / tỷ giá / nâng hạng.
- KQKD, kiểm toán, M&A, thay đổi lãnh đạo.
- Biến động thị trường: bán tháo, call margin, force sell…
- Từ khóa có nằm ngay trong **title** hay chỉ ở body.
- Có số liệu `%`, `tỷ đồng` hay không.
- Nguồn có tính chính thống/cao hay không.
- Bài opinion/dự báo bị trừ điểm nếu không có hard event.

Mỗi người dùng có thể chọn threshold từ **50–95** trong tab Alerts.

---

## 10. Email Digest

Một email gom nhiều tin thay vì spam từng bài:

```text
MARKET INTELLIGENCE
11/09/2026 · 09:00

CRITICAL · 94/100
[Tiêu đề]
Ticker: ...
Impact: ...
Scope: ...
Summary: ...
Vì sao urgent: ...
Đọc bài gốc ↗
```

Nếu một bài đã gửi cho A nhưng chưa gửi cho B, hệ thống vẫn xử lý độc lập nhờ `article_deliveries`.

---

## 11. Luồng hoàn chỉnh

```text
Every 20 minutes
       ↓
   Fetch News
       ↓
 Remove duplicates
       ↓
 Detect ticker/type
       ↓
 Urgency 0–100
 Impact / Scope
       ↓
    Supabase
       ↓
 User threshold filter
       ↓
Per-user deduplication
       ↓
07 / 09 / 12 / 17
       ↓
   Gmail Digest
```

---

## 12. Lưu ý khi deploy

- Scheduled GitHub Actions chạy trên default branch.
- Cron có thể có một độ trễ nhỏ khi GitHub Actions đang tải cao; lịch cấu hình vẫn là đúng 07:00 / 09:00 / 12:00 / 17:00 theo timezone Việt Nam.
- Không commit `.env`, service-role key hoặc Gmail App Password.
- Với production nhiều user, bước tiếp theo nên là login/authentication và Gmail OAuth thay cho App Password.
