import calendar
import html
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

import feedparser
from bs4 import BeautifulSoup

from urgency import calculate_urgency
from storage import save_article, url_hash

COMPANY_NAMES = {
    "FPT": "CTCP FPT", "SSI": "Chứng khoán SSI", "VIC": "Vingroup",
    "VHM": "Vinhomes", "VCB": "Vietcombank", "BID": "BIDV",
    "CTG": "VietinBank", "TCB": "Techcombank", "MBB": "MB Bank",
    "VPB": "VPBank", "HPG": "Hòa Phát", "HSG": "Hoa Sen",
    "NKG": "Nam Kim", "MWG": "Thế Giới Di Động", "VNM": "Vinamilk",
    "GAS": "PV GAS", "PLX": "Petrolimex", "VND": "Chứng khoán VNDirect",
    "HCM": "Chứng khoán HSC", "STB": "Sacombank", "ACB": "ACB",
    "MSB": "MSB", "NVB": "NCB", "SGB": "Saigonbank", "TPB": "TPBank",
    "DBC": "Dabaco", "MML": "Masan MEATLife", "HAG": "Hoàng Anh Gia Lai",
    "DGW": "Digiworld", "PVS": "PVS", "KDH": "Khang Điền", "NLG": "Nam Long",
}

DEFAULT_TICKERS = "FPT,TCB,VIC,VHM,PVS,SSI,VCB,BID,CTG,MBB,VPB,HPG,MWG,VNM,GAS"


def clean_text(raw: str) -> str:
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parsed_entry_time(entry):
    if entry.get("published_parsed"):
        return datetime.fromtimestamp(calendar.timegm(entry.published_parsed), tz=timezone.utc)
    if entry.get("updated_parsed"):
        return datetime.fromtimestamp(calendar.timegm(entry.updated_parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


def classify_news(text: str) -> str:
    s = text.lower()
    if any(k in s for k in ["trái phiếu", "bond", "lô trái phiếu"]):
        return "Trái phiếu"
    if any(k in s for k in ["lãi suất", "tỷ giá", "fed", "gdp", "cpi", "lạm phát", "vn-index", "ngân hàng nhà nước", "thuế", "nghị định"]):
        return "Vĩ mô / Chính sách"
    if any(k in s for k in ["ngành", "thép", "ngân hàng", "bất động sản", "công nghệ", "bán lẻ", "dầu khí", "hàng không"]):
        return "Ngành"
    return "Doanh nghiệp"


def fetch_ticker_news(ticker: str, days: int = 2, max_items: int = 20):
    ticker = ticker.strip().upper()
    company = COMPANY_NAMES.get(ticker, ticker)
    query = f'"{ticker}" "{company}" (cổ phiếu OR chứng khoán OR doanh nghiệp) when:{days}d'
    url = "https://news.google.com/rss/search?" + f"q={quote_plus(query)}&hl=vi&gl=VN&ceid=VN:vi"
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for entry in feed.entries:
        published = parsed_entry_time(entry)
        if published < cutoff:
            continue
        title = clean_text(entry.get("title", ""))
        summary = clean_text(entry.get("summary", ""))
        combined = f"{title} {summary}".upper()
        if ticker not in combined and company.upper() not in combined:
            continue
        source = "Google News"
        src = entry.get("source")
        if isinstance(src, dict):
            source = src.get("title") or source
        out.append({
            "ticker": ticker,
            "title": title,
            "summary": summary,
            "source": source,
            "url": entry.get("link", ""),
            "published_at": published.isoformat(),
        })
        if len(out) >= max_items:
            break
    return out


def run_update():
    tickers = [x.strip().upper() for x in (os.getenv("WATCH_TICKERS", "").strip() or DEFAULT_TICKERS).split(",") if x.strip()]
    all_rows = {}
    for ticker in tickers:
        for item in fetch_ticker_news(ticker, days=int(os.getenv("NEWS_LOOKBACK_DAYS", "2")), max_items=int(os.getenv("NEWS_MAX_PER_TICKER", "20"))):
            key = item["url"] or item["title"].lower()
            if key not in all_rows:
                all_rows[key] = {**item, "tickers": set()}
            all_rows[key]["tickers"].add(ticker)

    saved = 0
    for item in all_rows.values():
        tick_list = sorted(item.pop("tickers"))
        urgency = calculate_urgency(item["title"], item["summary"], item["source"], tick_list)
        payload = {
            **item,
            "tickers": tick_list,
            "url_hash": url_hash(item.get("url", ""), item.get("title", "")),
            "news_type": classify_news(f"{item['title']} {item['summary']}"),
            "urgency_score": urgency["score"],
            "urgency_level": urgency["level"],
            "impact": urgency["impact"],
            "market_scope": urgency["market_scope"],
            "reasons": urgency["reasons"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        save_article(payload)
        saved += 1
    return saved


if __name__ == "__main__":
    n = run_update()
    print(f"Saved/updated {n} articles")
