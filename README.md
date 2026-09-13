# Market Intelligence V5.1

Streamlit dashboard for Vietnamese investors with broad-market news scanning, urgency scoring, market synthesis, stock investment-thesis generation and scheduled Resend email digests.

## Tabs

- **Market Intelligence** — broad market synthesis plus deep scan by selected stock codes.
- **Investment Thesis** — combines news flow into Bull case, Bear case, Catalysts, Risks and a confidence level.
- **Alerts & Urgency** — Vietnam + international market radar, urgency filtering and email subscriptions.

## Background schedule

- News scanner: every 20 minutes.
- Digest delivery: 07:00, 09:00, 12:00, 17:00, timezone `Asia/Ho_Chi_Minh`.

## 1. Install locally

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

## 2. Supabase

Create a Supabase project and run the entire `supabase_schema.sql` in SQL Editor.

Required server-side secrets:

```text
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_KEY=sb_secret_xxxxxxxxx
```

Do not commit the secret key.

## 3. Resend

Create a Resend account and an API key. V5.1 calls the official Resend REST Email API over HTTPS.

GitHub repository secret:

```text
RESEND_API_KEY=re_xxxxxxxxx
```

GitHub repository variable:

```text
RESEND_FROM=Stock News Intelligence <onboarding@resend.dev>
```

For initial testing, `onboarding@resend.dev` is suitable only when the recipient is the email tied to your Resend account. For multiple public recipients, verify a domain in Resend and change `RESEND_FROM`, for example:

```text
RESEND_FROM=Market Intelligence <alerts@updates.yourdomain.com>
```

## 4. GitHub Actions configuration

### Secrets

```text
SUPABASE_URL
SUPABASE_KEY
RESEND_API_KEY
```

### Variables

```text
RESEND_FROM
ALERT_RECIPIENTS   # optional test fallback
```

V5.1 no longer needs `WATCH_TICKERS`.

## 5. Streamlit secrets

At minimum:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "sb_secret_xxxxxxxxx"
```

Optional AI summaries:

```toml
OPENAI_API_KEY = "..."
OPENAI_MODEL = "..."
```

## 6. First test

1. GitHub → Actions → **Update Financial News** → Run workflow.
2. Supabase → `articles` → verify rows exist.
3. Open the Streamlit app → **Alerts & Urgency**.
4. Register a recipient email and threshold.
5. GitHub → Actions → **Send Market Urgency Digest** → Run workflow.
6. Check `article_deliveries` to verify per-recipient deduplication.

## Coverage model

The scanner runs multiple broad streams instead of scanning only user-selected tickers:

- Listed-company and corporate news
- VN-Index / VN30 / HNX / UPCoM market news
- State Bank, rates, FX, credit, CPI, GDP and policy
- Banking, property and other major sectors
- Corporate/legal/market-risk events
- Fed/FOMC, US equities, China/Asia
- Oil, gold, OPEC, trade policy and geopolitical shocks

No news aggregator can guarantee literally every article on the internet. V5.1 is designed for broad, high-frequency coverage and prioritization rather than a finite ticker watchlist.

## Disclaimer

The dashboard is an information and research tool. Investment Thesis is based on news flow and is not a personalized recommendation or target-price valuation.
