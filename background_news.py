import calendar
import html
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

import feedparser
from bs4 import BeautifulSoup

from analysis_engine import classify_region, detect_sector, extract_tickers
from urgency import calculate_urgency
from storage import save_article, url_hash

# V5.1 scans broad market streams instead of a user-selected ticker watchlist.
MARKET_STREAMS = [
    {"name": "VN Listed Companies", "region": "Việt Nam", "query": '("cổ phiếu" OR "mã cổ phiếu" OR HOSE OR HNX OR UPCoM) (doanh nghiệp OR lợi nhuận OR doanh thu OR cổ tức OR phát hành OR M&A)'},
    {"name": "VN Market", "region": "Việt Nam", "query": '(VN-Index OR VN30 OR HNX-Index OR UPCoM-Index) (chứng khoán OR thị trường OR thanh khoản OR khối ngoại OR margin)'},
    {"name": "VN Macro", "region": "Việt Nam", "query": '("Ngân hàng Nhà nước" OR NHNN OR lãi suất OR tỷ giá OR tín dụng OR CPI OR GDP OR lạm phát) Việt Nam'},
    {"name": "VN Policy", "region": "Việt Nam", "query": '("Bộ Tài chính" OR "Ủy ban Chứng khoán" OR UBCK OR Chính phủ OR Quốc hội) (chứng khoán OR thuế OR nghị định OR thông tư OR thị trường vốn)'},
    {"name": "VN Corporate Risk", "region": "Việt Nam", "query": '(khởi tố OR "bắt tạm giam" OR thanh tra OR "hủy niêm yết" OR "đình chỉ giao dịch" OR kiểm toán OR "chậm thanh toán trái phiếu") (doanh nghiệp OR cổ phiếu)'},
    {"name": "Banking", "region": "Việt Nam", "query": '(ngân hàng OR tín dụng OR nợ xấu OR NIM OR CASA) (cổ phiếu OR chứng khoán OR lợi nhuận)'},
    {"name": "Real Estate", "region": "Việt Nam", "query": '(bất động sản OR địa ốc OR nhà ở OR đất đai) (cổ phiếu OR doanh nghiệp OR trái phiếu OR pháp lý)'},
    {"name": "Industry", "region": "Việt Nam", "query": '(thép OR dầu khí OR bán lẻ OR công nghệ OR thủy sản OR phân bón OR logistics OR hàng không OR điện) (cổ phiếu OR doanh nghiệp OR lợi nhuận)'},
    {"name": "US Fed", "region": "Quốc tế", "query": '(Fed OR FOMC OR Powell OR "US CPI" OR PCE OR "nonfarm payrolls") (stocks OR markets OR rates)'},
    {"name": "US Markets", "region": "Quốc tế", "query": '("S&P 500" OR Nasdaq OR "Dow Jones" OR "Wall Street") (stocks OR market)'},
    {"name": "China Asia", "region": "Quốc tế", "query": '(China economy OR PBOC OR yuan OR "Hang Seng" OR Nikkei OR Kospi) (markets OR stocks)'},
    {"name": "Commodities", "region": "Quốc tế", "query": '(Brent OR WTI OR OPEC OR "oil price" OR "gold price") markets'},
    {"name": "Global Trade", "region": "Quốc tế", "query": '(tariff OR "trade war" OR sanctions OR geopolitical OR conflict) (markets OR stocks OR economy)'},
]


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
    if any(k in s for k in ["khởi tố", "đình chỉ giao dịch", "hủy niêm yết", "thanh tra", "kiểm toán"]):
        return "Pháp lý / Quản trị"
    if any(k in s for k in ["trái phiếu", "bond", "lô trái phiếu", "vỡ nợ", "chậm thanh toán"]):
        return "Trái phiếu / Tín dụng"
    if any(k in s for k in ["lãi suất", "tỷ giá", "fed", "fomc", "gdp", "cpi", "lạm phát", "nhnn", "ngân hàng nhà nước", "thuế quan", "tariff"]):
        return "Vĩ mô / Chính sách"
    if any(k in s for k in ["vn-index", "vn30", "s&p 500", "nasdaq", "dow jones", "wall street", "hang seng", "nikkei", "kospi"]):
        return "Thị trường"
    if any(k in s for k in ["lợi nhuận", "doanh thu", "kết quả kinh doanh", "cổ tức", "phát hành", "m&a", "sáp nhập"]):
        return "Doanh nghiệp"
    return "Ngành / Thị trường"


def fetch_stream(stream: dict, days: int = 2, max_items: int = 25):
    query = f"{stream['query']} when:{days}d"
    # vi/VN keeps Vietnam relevance while still surfacing major international developments.
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
        if not title:
            continue
        source = "Google News"
        src = entry.get("source")
        if isinstance(src, dict):
            source = src.get("title") or source
        combined = f"{title} {summary}"
        out.append({
            "title": title,
            "summary": summary,
            "source": source,
            "url": entry.get("link", ""),
            "published_at": published.isoformat(),
            "region": classify_region(combined, stream.get("region", "")),
            "market_topic": detect_sector(combined),
            "stream": stream.get("name", "Market"),
        })
        if len(out) >= max_items:
            break
    return out


def run_update():
    days = int(os.getenv("NEWS_LOOKBACK_DAYS", "2"))
    max_per_stream = int(os.getenv("NEWS_MAX_PER_STREAM", "25"))
    all_rows = {}

    for stream in MARKET_STREAMS:
        for item in fetch_stream(stream, days=days, max_items=max_per_stream):
            key = item.get("url") or re.sub(r"\W+", " ", item["title"].lower()).strip()
            if key not in all_rows:
                all_rows[key] = {**item, "streams": set()}
            all_rows[key]["streams"].add(stream["name"])

    saved = 0
    for item in all_rows.values():
        item.pop("streams", None)
        combined = f"{item['title']} {item['summary']}"
        tickers = extract_tickers(combined)
        urgency = calculate_urgency(item["title"], item["summary"], item["source"], tickers)
        payload = {
            **item,
            "tickers": tickers,
            "url_hash": url_hash(item.get("url", ""), item.get("title", "")),
            "news_type": classify_news(combined),
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
    print(f"Saved/updated {n} broad-market articles from {len(MARKET_STREAMS)} streams")
