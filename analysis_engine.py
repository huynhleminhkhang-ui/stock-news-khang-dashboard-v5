import re
from collections import Counter, defaultdict
from typing import Iterable

SECTOR_KEYWORDS = {
    "Ngân hàng": ["ngân hàng", "tín dụng", "nợ xấu", "lãi suất", "bank"],
    "Bất động sản": ["bất động sản", "địa ốc", "nhà ở", "đất đai", "chung cư"],
    "Chứng khoán": ["chứng khoán", "môi giới", "margin", "vn-index", "vn30"],
    "Thép / Vật liệu": ["thép", "quặng sắt", "tôn mạ", "xi măng", "vật liệu xây dựng"],
    "Dầu khí / Năng lượng": ["dầu khí", "giá dầu", "brent", "wti", "opec", "điện", "năng lượng"],
    "Công nghệ": ["công nghệ", "ai", "bán dẫn", "phần mềm", "data center"],
    "Bán lẻ / Tiêu dùng": ["bán lẻ", "tiêu dùng", "siêu thị", "điện máy", "sữa"],
    "Xuất khẩu": ["xuất khẩu", "thủy sản", "dệt may", "gỗ", "cao su", "cà phê"],
    "Logistics / Hàng không": ["logistics", "cảng biển", "vận tải", "hàng không"],
}

GLOBAL_HINTS = [
    "fed", "fomc", "powell", "s&p 500", "nasdaq", "dow jones", "wall street",
    "mỹ", "hoa kỳ", "trung quốc", "pboc", "hang seng", "nikkei", "kospi",
    "opec", "brent", "wti", "ecb", "boj", "thuế quan", "tariff", "sanctions",
]

VIETNAM_HINTS = [
    "vn-index", "vn30", "hose", "hnx", "upcom", "ngân hàng nhà nước", "nhnn",
    "việt nam", "bộ tài chính", "ủy ban chứng khoán", "ubck", "tổng cục thống kê",
]


def extract_tickers(text: str) -> list[str]:
    """Extract likely Vietnamese stock symbols without requiring a preselected universe."""
    raw = text or ""
    found = set()
    patterns = [
        r"(?:mã|cổ phiếu|cp)\s+([A-Z]{3})(?![A-Z])",
        r"(?:HOSE|HNX|UPCOM)\s*[:\-]\s*([A-Z]{3})(?![A-Z])",
        r"\[([A-Z]{3})\]",
        r"\(([A-Z]{3})\)",
    ]
    for pattern in patterns:
        found.update(re.findall(pattern, raw, flags=re.I))

    # Upper-case symbols in Vietnamese finance headlines are often tickers, but avoid common acronyms.
    stop = {
        "USD", "VND", "GDP", "CPI", "PCE", "FED", "CEO", "CFO", "ETF", "IPO", "M&A",
        "HNX", "HOSE", "UPCOM", "VN30", "SSI",  # SSI is restored below when context supports it
        "NAV", "EPS", "ROE", "ROA", "NIM", "CAR", "NPL", "AI", "API", "OPEC", "ECB", "BOJ",
    }
    upper = set(re.findall(r"(?<![A-Z0-9])([A-Z]{3})(?![A-Z0-9])", raw))
    for token in upper:
        if token not in stop:
            found.add(token)
    if re.search(r"(?:mã|cổ phiếu|chứng khoán)\s+SSI\b|\bSSI\s+(?:tăng|giảm|đạt|ghi nhận)", raw, flags=re.I):
        found.add("SSI")
    return sorted({x.upper() for x in found if len(x) == 3})


def classify_region(text: str, hinted_region: str = "") -> str:
    if hinted_region:
        return hinted_region
    s = (text or "").lower()
    vn = sum(k in s for k in VIETNAM_HINTS)
    glob = sum(k in s for k in GLOBAL_HINTS)
    if glob > vn:
        return "Quốc tế"
    return "Việt Nam"


def detect_sector(text: str) -> str:
    s = (text or "").lower()
    scored = [(name, sum(k in s for k in keys)) for name, keys in SECTOR_KEYWORDS.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0] if scored and scored[0][1] else "Đa ngành / Thị trường"


def _impact_score(article: dict) -> float:
    impact = article.get("impact", "Neutral")
    direction = {"Positive": 1, "Negative": -1, "Mixed": 0, "Neutral": 0}.get(impact, 0)
    urgency = max(10, int(article.get("urgency_score", 0)))
    return direction * urgency


def market_synthesis(articles: Iterable[dict], max_headlines: int = 4) -> dict:
    rows = list(articles or [])
    if not rows:
        return {
            "tone": "Chưa đủ dữ liệu",
            "headline": "Chưa có đủ bài báo để tổng kết thị trường.",
            "bullets": [],
            "sectors": [],
            "risks": [],
            "opportunities": [],
        }

    directional = sum(_impact_score(a) for a in rows)
    active = sum(max(10, int(a.get("urgency_score", 0))) for a in rows)
    ratio = directional / active if active else 0
    if ratio >= 0.18:
        tone = "Tích cực"
    elif ratio <= -0.18:
        tone = "Thận trọng"
    else:
        tone = "Trung lập / phân hóa"

    regions = Counter((a.get("region") or classify_region(f"{a.get('title','')} {a.get('summary','')}")) for a in rows)
    sectors = Counter((a.get("market_topic") or detect_sector(f"{a.get('title','')} {a.get('summary','')}")) for a in rows)
    types = Counter(a.get("news_type") or "Khác" for a in rows)
    urgent = [a for a in rows if int(a.get("urgency_score", 0)) >= 70]
    neg = sorted([a for a in rows if a.get("impact") == "Negative"], key=lambda x: int(x.get("urgency_score", 0)), reverse=True)
    pos = sorted([a for a in rows if a.get("impact") == "Positive"], key=lambda x: int(x.get("urgency_score", 0)), reverse=True)

    top_sectors = [name for name, count in sectors.most_common(3) if name != "Đa ngành / Thị trường"]
    top_types = ", ".join(name for name, _ in types.most_common(3))
    bullets = [
        f"Dòng tin hiện nghiêng về **{tone.lower()}**, dựa trên {len(rows)} bài đang được hệ thống tổng hợp.",
        f"Độ phủ: **{regions.get('Việt Nam', 0)} tin Việt Nam** và **{regions.get('Quốc tế', 0)} tin quốc tế**; {len(urgent)} tin đạt mức HIGH/CRITICAL.",
        f"Chủ đề xuất hiện nhiều: **{top_types or 'chưa có chủ đề chi phối'}**.",
    ]
    if top_sectors:
        bullets.append("Nhóm ngành được nhắc nhiều nhất: **" + ", ".join(top_sectors) + "**.")

    headline = (
        "Thị trường đang có tín hiệu tích cực nhưng vẫn cần chọn lọc theo catalyst và chất lượng lợi nhuận."
        if tone == "Tích cực" else
        "Luồng tin hiện thiên về rủi ro; nên ưu tiên quản trị vị thế và theo dõi catalyst xác nhận."
        if tone == "Thận trọng" else
        "Luồng tin đang phân hóa; quyết định nên dựa trên từng ngành và từng doanh nghiệp thay vì đi theo thị trường chung."
    )

    def short(a):
        t = (a.get("title") or "").strip()
        return t[:180] + ("…" if len(t) > 180 else "")

    return {
        "tone": tone,
        "headline": headline,
        "bullets": bullets,
        "sectors": sectors.most_common(5),
        "risks": [short(a) for a in neg[:max_headlines]],
        "opportunities": [short(a) for a in pos[:max_headlines]],
    }


def investment_thesis(ticker: str, articles: Iterable[dict]) -> dict:
    ticker = (ticker or "").strip().upper()
    rows = []
    for a in articles or []:
        tickers = a.get("tickers") or []
        if isinstance(tickers, str):
            tickers = [tickers]
        title = a.get("title", "")
        if ticker in {str(x).upper() for x in tickers} or re.search(rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])", title.upper()):
            rows.append(a)

    rows.sort(key=lambda x: (int(x.get("urgency_score", 0)), str(x.get("published_at", ""))), reverse=True)
    if not rows:
        return {
            "ticker": ticker,
            "stance": "CHƯA ĐỦ DỮ LIỆU",
            "confidence": "Thấp",
            "summary": f"Chưa có đủ news flow gần đây để hình thành luận điểm đầu tư cho {ticker}.",
            "bull": [], "bear": [], "catalysts": [], "risks": [], "evidence_count": 0,
        }

    positive = [a for a in rows if a.get("impact") == "Positive"]
    negative = [a for a in rows if a.get("impact") == "Negative"]
    pos_score = sum(max(20, int(a.get("urgency_score", 0))) for a in positive)
    neg_score = sum(max(20, int(a.get("urgency_score", 0))) for a in negative)

    if pos_score > neg_score * 1.25 and len(positive) >= 1:
        stance = "TÍCH CỰC CÓ ĐIỀU KIỆN"
    elif neg_score > pos_score * 1.25 and len(negative) >= 1:
        stance = "THẬN TRỌNG"
    else:
        stance = "TRUNG LẬP / CHỜ XÁC NHẬN"

    confidence = "Cao" if len(rows) >= 8 else "Trung bình" if len(rows) >= 4 else "Thấp"

    def titles(xs, n=4):
        out = []
        for a in xs[:n]:
            t = (a.get("title") or "").strip()
            if t and t not in out:
                out.append(t)
        return out

    catalysts = sorted(positive, key=lambda x: int(x.get("urgency_score", 0)), reverse=True)
    risks = sorted(negative, key=lambda x: int(x.get("urgency_score", 0)), reverse=True)
    summary = (
        f"Luận điểm news-flow cho {ticker} hiện ở trạng thái **{stance}**. "
        f"Hệ thống ghi nhận {len(positive)} tín hiệu tích cực, {len(negative)} tín hiệu tiêu cực trong {len(rows)} bài liên quan. "
        "Kết luận này phản ánh thông tin/catalyst gần đây, không phải định giá mục tiêu hay khuyến nghị mua/bán."
    )
    return {
        "ticker": ticker,
        "stance": stance,
        "confidence": confidence,
        "summary": summary,
        "bull": titles(positive),
        "bear": titles(negative),
        "catalysts": titles(catalysts, 3),
        "risks": titles(risks, 3),
        "evidence_count": len(rows),
    }
