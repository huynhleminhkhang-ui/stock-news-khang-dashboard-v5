import html
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo


def _impact_label(value: str) -> str:
    return {
        "Positive": "📈 Tích cực",
        "Negative": "📉 Tiêu cực",
        "Mixed": "↔️ Trái chiều",
        "Neutral": "➖ Trung lập",
    }.get(value or "", value or "➖ Trung lập")


def build_digest_html(articles: list[dict], now=None) -> str:
    now = now or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    cards = []
    for a in articles:
        score = int(a.get("urgency_score", 0))
        color = "#dc2626" if score >= 90 else "#f97316" if score >= 70 else "#eab308"
        tickers = a.get("tickers") or []
        if isinstance(tickers, str):
            tickers = [tickers]
        reasons = a.get("reasons") or []
        if isinstance(reasons, str):
            reasons = [reasons]
        summary = (a.get("summary") or "").strip()
        if len(summary) > 700:
            summary = summary[:697].rstrip() + "..."
        cards.append(f"""
        <div style="border:1px solid #e2e8f0;border-radius:14px;padding:18px;margin:14px 0;background:#ffffff">
          <div style="font-size:13px;font-weight:700;color:{color};">{html.escape(a.get('urgency_level','HIGH'))} · {score}/100</div>
          <div style="font-size:18px;font-weight:800;color:#0f172a;margin:6px 0 8px">{html.escape(a.get('title',''))}</div>
          <div style="font-size:13px;color:#64748b;margin-bottom:10px">{html.escape(a.get('source',''))} · {html.escape(', '.join(tickers) or 'Market')}</div>
          <div style="font-size:14px;color:#334155;line-height:1.6">{html.escape(summary)}</div>
          <div style="margin-top:12px;font-size:13px;color:#475569"><b>Impact:</b> {_impact_label(a.get('impact',''))} &nbsp; | &nbsp; <b>Scope:</b> {html.escape(a.get('market_scope',''))}</div>
          <div style="margin-top:6px;font-size:13px;color:#475569"><b>Vì sao urgent:</b> {html.escape(' · '.join(reasons[:3]))}</div>
          <div style="margin-top:14px"><a href="{html.escape(a.get('url',''))}" style="background:#2563eb;color:white;text-decoration:none;padding:8px 12px;border-radius:8px;font-size:13px;font-weight:700">Đọc bài gốc ↗</a></div>
        </div>
        """)

    critical = sum(int(a.get("urgency_score", 0)) >= 90 for a in articles)
    return f"""
    <!doctype html><html><body style="margin:0;background:#f8fafc;font-family:Arial,sans-serif;color:#0f172a">
    <div style="max-width:760px;margin:auto;padding:24px">
      <div style="background:#0f172a;color:#fff;padding:22px;border-radius:16px">
        <div style="font-size:12px;letter-spacing:1.4px;color:#93c5fd;font-weight:700">MARKET INTELLIGENCE</div>
        <div style="font-size:24px;font-weight:800;margin-top:6px">Stock News Urgency Digest</div>
        <div style="font-size:14px;color:#cbd5e1;margin-top:7px">{now.strftime('%d/%m/%Y · %H:%M')} · {len(articles)} tin HIGH/CRITICAL · {critical} CRITICAL</div>
      </div>
      {''.join(cards)}
      <div style="font-size:12px;color:#94a3b8;text-align:center;margin:22px 0">Chỉ gửi các tin vượt ngưỡng urgency đã cấu hình. Không phải khuyến nghị đầu tư.</div>
    </div></body></html>
    """


def send_digest(recipient: str, articles: list[dict]):
    user = os.getenv("GMAIL_USER", "").strip()
    password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not user or not password:
        raise RuntimeError("Missing GMAIL_USER or GMAIL_APP_PASSWORD")

    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    msg = EmailMessage()
    msg["From"] = f"{os.getenv('EMAIL_FROM_NAME', 'Stock News Intelligence')} <{user}>"
    msg["To"] = recipient
    msg["Subject"] = f"📈 Market Urgency Digest · {now.strftime('%H:%M %d/%m')}"
    msg.set_content("Market Urgency Digest. Vui lòng mở email ở chế độ HTML để xem đầy đủ.")
    msg.add_alternative(build_digest_html(articles, now), subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
