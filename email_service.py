import html
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from analysis_engine import market_synthesis


def _impact_label(value: str) -> str:
    return {
        "Positive": "📈 Tích cực",
        "Negative": "📉 Tiêu cực",
        "Mixed": "↔️ Trái chiều",
        "Neutral": "➖ Trung lập",
    }.get(value or "", value or "➖ Trung lập")


def build_digest_html(articles: list[dict], now=None) -> str:
    now = now or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    synth = market_synthesis(articles)
    synthesis_bullets = "".join(
        f'<li style="margin:7px 0">{html.escape(b.replace("**", ""))}</li>'
        for b in synth.get("bullets", [])
    )
    opportunities = "".join(f"<li>{html.escape(x)}</li>" for x in synth.get("opportunities", [])[:3]) or "<li>Chưa có catalyst tích cực đủ mạnh trong batch hiện tại.</li>"
    risks = "".join(f"<li>{html.escape(x)}</li>" for x in synth.get("risks", [])[:3]) or "<li>Chưa có rủi ro HIGH/CRITICAL nổi bật trong batch hiện tại.</li>"

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
          <div style="font-size:13px;color:#64748b;margin-bottom:10px">{html.escape(a.get('source',''))} · {html.escape(a.get('region',''))} · {html.escape(', '.join(tickers) or 'Market')}</div>
          <div style="font-size:14px;color:#334155;line-height:1.6">{html.escape(summary)}</div>
          <div style="margin-top:12px;font-size:13px;color:#475569"><b>Impact:</b> {_impact_label(a.get('impact',''))} &nbsp; | &nbsp; <b>Scope:</b> {html.escape(a.get('market_scope',''))} &nbsp; | &nbsp; <b>Topic:</b> {html.escape(a.get('market_topic',''))}</div>
          <div style="margin-top:6px;font-size:13px;color:#475569"><b>Vì sao urgent:</b> {html.escape(' · '.join(reasons[:3]))}</div>
          <div style="margin-top:14px"><a href="{html.escape(a.get('url',''))}" style="background:#2563eb;color:white;text-decoration:none;padding:8px 12px;border-radius:8px;font-size:13px;font-weight:700">Đọc bài gốc ↗</a></div>
        </div>
        """)

    critical = sum(int(a.get("urgency_score", 0)) >= 90 for a in articles)
    return f"""
    <!doctype html><html><body style="margin:0;background:#f8fafc;font-family:Arial,sans-serif;color:#0f172a">
    <div style="max-width:760px;margin:auto;padding:24px">
      <div style="background:#0f172a;color:#fff;padding:22px;border-radius:16px">
        <div style="font-size:12px;letter-spacing:1.4px;color:#93c5fd;font-weight:700">MARKET INTELLIGENCE V5.1</div>
        <div style="font-size:24px;font-weight:800;margin-top:6px">Urgency & Market Digest</div>
        <div style="font-size:14px;color:#cbd5e1;margin-top:7px">{now.strftime('%d/%m/%Y · %H:%M')} · {len(articles)} tin đạt ngưỡng · {critical} CRITICAL</div>
      </div>
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:14px;padding:18px;margin:14px 0">
        <div style="font-size:17px;font-weight:800;color:#1e3a8a">Tổng kết thị trường: {html.escape(synth.get('tone',''))}</div>
        <div style="font-size:14px;color:#334155;line-height:1.6;margin-top:8px">{html.escape(synth.get('headline',''))}</div>
        <ul style="font-size:14px;color:#334155;line-height:1.55">{synthesis_bullets}</ul>
        <div style="font-size:14px;font-weight:700;color:#166534;margin-top:10px">Catalyst / cơ hội đáng theo dõi</div>
        <ul style="font-size:13px;color:#334155;line-height:1.5">{opportunities}</ul>
        <div style="font-size:14px;font-weight:700;color:#991b1b;margin-top:10px">Rủi ro đáng theo dõi</div>
        <ul style="font-size:13px;color:#334155;line-height:1.5">{risks}</ul>
      </div>
      {''.join(cards)}
      <div style="font-size:12px;color:#94a3b8;text-align:center;margin:22px 0">Thông tin phục vụ sàng lọc và nghiên cứu, không phải khuyến nghị đầu tư cá nhân.</div>
    </div></body></html>
    """


def send_digest(recipient: str, articles: list[dict]):
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing RESEND_API_KEY")
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    from_addr = os.getenv("RESEND_FROM", "Stock News Intelligence <onboarding@resend.dev>").strip()
    payload = {
        "from": from_addr,
        "to": [recipient],
        "subject": f"📈 Market Urgency Digest · {now.strftime('%H:%M %d/%m')}",
        "html": build_digest_html(articles, now),
    }
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "market-intelligence-v5.1/1.0",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
