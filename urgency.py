import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Iterable


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class UrgencyResult:
    score: int
    level: str
    impact: str
    category: str
    market_scope: str
    reasons: list[str]

    def to_dict(self):
        return asdict(self)


# phrase, points, reason, category, scope, impact
CRITICAL_RULES = [
    ("khởi tố", 60, "Sự kiện pháp lý nghiêm trọng", "Pháp lý", "Doanh nghiệp", "Negative"),
    ("bắt tạm giam", 65, "Lãnh đạo/cá nhân bị bắt tạm giam", "Pháp lý", "Doanh nghiệp", "Negative"),
    ("bắt giữ", 58, "Sự kiện bắt giữ", "Pháp lý", "Doanh nghiệp", "Negative"),
    ("hủy niêm yết", 65, "Rủi ro hủy niêm yết", "Niêm yết", "Doanh nghiệp", "Negative"),
    ("đình chỉ giao dịch", 65, "Đình chỉ giao dịch", "Niêm yết", "Doanh nghiệp", "Negative"),
    ("vỡ nợ", 65, "Rủi ro vỡ nợ", "Tín dụng / Trái phiếu", "Doanh nghiệp", "Negative"),
    ("mất khả năng thanh toán", 65, "Rủi ro mất khả năng thanh toán", "Tín dụng / Trái phiếu", "Doanh nghiệp", "Negative"),
    ("từ chối đưa ra ý kiến", 55, "Kiểm toán từ chối đưa ra ý kiến", "Kiểm toán", "Doanh nghiệp", "Negative"),
    ("nghi ngờ khả năng hoạt động liên tục", 55, "Nghi ngờ khả năng hoạt động liên tục", "Kiểm toán", "Doanh nghiệp", "Negative"),
    ("thao túng chứng khoán", 55, "Nghi vấn/vi phạm thao túng chứng khoán", "Pháp lý", "Thị trường", "Negative"),
    ("call margin", 48, "Áp lực call margin", "Thị trường", "Thị trường", "Negative"),
    ("force sell", 48, "Áp lực bán giải chấp", "Thị trường", "Thị trường", "Negative"),
    ("bán giải chấp", 48, "Áp lực bán giải chấp", "Thị trường", "Thị trường", "Negative"),
]

MACRO_RULES = [
    ("lãi suất điều hành", 38, "Thay đổi/kỳ vọng lãi suất điều hành", "Vĩ mô / Lãi suất", "Toàn thị trường"),
    ("ngân hàng nhà nước", 22, "Thông tin từ Ngân hàng Nhà nước", "Vĩ mô / Chính sách", "Toàn thị trường"),
    ("nhnn", 22, "Thông tin từ NHNN", "Vĩ mô / Chính sách", "Toàn thị trường"),
    ("fed", 20, "Thông tin chính sách Fed", "Quốc tế / Lãi suất", "Toàn thị trường"),
    ("fomc", 24, "Thông tin FOMC", "Quốc tế / Lãi suất", "Toàn thị trường"),
    ("nâng hạng thị trường", 45, "Thông tin nâng hạng thị trường", "Thị trường", "Toàn thị trường"),
    ("ftse russell", 26, "Thông tin FTSE Russell", "Thị trường", "Toàn thị trường"),
    ("msci", 22, "Thông tin MSCI", "Thị trường", "Toàn thị trường"),
    ("tỷ giá", 16, "Biến động/chính sách tỷ giá", "Vĩ mô / Tỷ giá", "Toàn thị trường"),
    ("cpi", 14, "Dữ liệu lạm phát", "Vĩ mô", "Toàn thị trường"),
    ("lạm phát", 14, "Thông tin lạm phát", "Vĩ mô", "Toàn thị trường"),
    ("thuế quan", 18, "Rủi ro/chính sách thuế quan", "Thương mại", "Theo ngành"),
    ("chống bán phá giá", 20, "Biện pháp chống bán phá giá", "Thương mại", "Theo ngành"),
    ("cấm xuất khẩu", 20, "Hạn chế xuất khẩu", "Thương mại", "Theo ngành"),
    ("cấm nhập khẩu", 20, "Hạn chế nhập khẩu", "Thương mại", "Theo ngành"),
    ("nonfarm payrolls", 16, "Dữ liệu việc làm Mỹ", "Quốc tế / Vĩ mô", "Toàn thị trường"),
    ("pce", 15, "Dữ liệu lạm phát PCE Mỹ", "Quốc tế / Vĩ mô", "Toàn thị trường"),
    ("s&p 500", 12, "Biến động chứng khoán Mỹ", "Quốc tế / Thị trường", "Toàn thị trường"),
    ("nasdaq", 12, "Biến động Nasdaq", "Quốc tế / Thị trường", "Toàn thị trường"),
    ("dow jones", 11, "Biến động Dow Jones", "Quốc tế / Thị trường", "Toàn thị trường"),
    ("pboc", 18, "Chính sách tiền tệ Trung Quốc", "Quốc tế / Vĩ mô", "Toàn thị trường"),
    ("opec", 16, "Thông tin nguồn cung dầu OPEC", "Quốc tế / Hàng hóa", "Theo ngành"),
    ("brent", 13, "Biến động giá dầu Brent", "Quốc tế / Hàng hóa", "Theo ngành"),
    ("wti", 13, "Biến động giá dầu WTI", "Quốc tế / Hàng hóa", "Theo ngành"),
    ("trừng phạt", 22, "Rủi ro địa chính trị/trừng phạt", "Địa chính trị", "Toàn thị trường"),
    ("sanctions", 22, "Rủi ro địa chính trị/trừng phạt", "Địa chính trị", "Toàn thị trường"),
]

COMPANY_RULES = [
    ("lỗ kỷ lục", 40, "Kết quả kinh doanh lỗ kỷ lục", "KQKD", "Doanh nghiệp", "Negative"),
    ("lỗ đột biến", 35, "Kết quả kinh doanh xấu đột biến", "KQKD", "Doanh nghiệp", "Negative"),
    ("lợi nhuận giảm mạnh", 24, "Lợi nhuận giảm mạnh", "KQKD", "Doanh nghiệp", "Negative"),
    ("lợi nhuận tăng mạnh", 28, "Lợi nhuận tăng mạnh", "KQKD", "Doanh nghiệp", "Positive"),
    ("lợi nhuận tăng đột biến", 35, "Lợi nhuận tăng đột biến", "KQKD", "Doanh nghiệp", "Positive"),
    ("vượt kế hoạch", 18, "Vượt kế hoạch kinh doanh", "KQKD", "Doanh nghiệp", "Positive"),
    ("trúng thầu", 18, "Trúng thầu/hợp đồng mới", "Hợp đồng", "Doanh nghiệp", "Positive"),
    ("ký hợp đồng", 15, "Hợp đồng mới", "Hợp đồng", "Doanh nghiệp", "Positive"),
    ("chào mua công khai", 25, "Chào mua công khai", "M&A", "Doanh nghiệp", "Mixed"),
    ("mua cổ phần chi phối", 25, "Giao dịch thay đổi quyền kiểm soát", "M&A", "Doanh nghiệp", "Mixed"),
    ("sáp nhập", 22, "Sự kiện M&A", "M&A", "Doanh nghiệp", "Mixed"),
    ("thoái vốn", 16, "Thoái vốn", "Sở hữu", "Doanh nghiệp", "Mixed"),
    ("chủ tịch từ nhiệm", 28, "Thay đổi lãnh đạo cấp cao", "Nhân sự", "Doanh nghiệp", "Negative"),
    ("tổng giám đốc từ nhiệm", 28, "Thay đổi lãnh đạo cấp cao", "Nhân sự", "Doanh nghiệp", "Negative"),
    ("ceo từ nhiệm", 28, "Thay đổi lãnh đạo cấp cao", "Nhân sự", "Doanh nghiệp", "Negative"),
    ("phát hành riêng lẻ", 15, "Phát hành riêng lẻ", "Vốn", "Doanh nghiệp", "Mixed"),
    ("phát hành thêm", 15, "Phát hành thêm", "Vốn", "Doanh nghiệp", "Mixed"),
    ("chậm thanh toán trái phiếu", 34, "Chậm thanh toán trái phiếu", "Tín dụng / Trái phiếu", "Doanh nghiệp", "Negative"),
    ("gia hạn trái phiếu", 24, "Gia hạn nghĩa vụ trái phiếu", "Tín dụng / Trái phiếu", "Doanh nghiệp", "Negative"),
    ("mua lại trái phiếu trước hạn", 17, "Mua lại trái phiếu trước hạn", "Trái phiếu", "Doanh nghiệp", "Positive"),
    ("kiểm toán ngoại trừ", 30, "Ý kiến kiểm toán ngoại trừ", "Kiểm toán", "Doanh nghiệp", "Negative"),
]

MARKET_STRESS = [
    ("bán tháo", 26, "Tâm lý bán tháo"),
    ("hoảng loạn", 20, "Tâm lý hoảng loạn"),
    ("giảm sàn", 18, "Biến động giá rất mạnh"),
    ("tăng trần", 14, "Biến động giá rất mạnh"),
    ("thủng hỗ trợ", 12, "Tín hiệu thị trường đáng chú ý"),
    ("lập đỉnh", 10, "Thiết lập đỉnh mới"),
]

POSITIVE_HINTS = ["tăng trưởng", "tăng mạnh", "kỷ lục", "vượt kế hoạch", "trúng thầu", "được phê duyệt", "mua lại trước hạn"]
NEGATIVE_HINTS = ["giảm mạnh", "thua lỗ", "bị phạt", "điều tra", "khởi tố", "nợ xấu", "vỡ nợ", "đình chỉ", "hủy niêm yết", "chậm thanh toán"]

HIGH_AUTHORITY_SOURCES = [
    "chính phủ", "ngân hàng nhà nước", "ủy ban chứng khoán", "ubck", "hose", "hnx", "vsd", "vsdC",
    "bộ tài chính", "tổng cục thống kê", "reuters", "bloomberg", "ftse russell", "msci",
]

OPINION_WORDS = ["nhận định", "dự báo", "chuyên gia cho rằng", "có thể", "kỳ vọng", "khuyến nghị", "góc nhìn"]


def calculate_urgency(title: str, summary: str = "", source: str = "", tickers: Iterable[str] | None = None) -> dict:
    title_n = _norm(title)
    text = _norm(f"{title} {summary}")
    source_n = _norm(source)
    score = 8  # baseline for a fresh finance article
    reasons: list[str] = []
    category = "Tin doanh nghiệp"
    scope = "Doanh nghiệp"
    explicit_impacts: list[str] = []

    # Title matches are more informative than body-only mentions.
    def matched_points(phrase: str, base: int) -> int:
        return base + (15 if phrase in title_n else 0)

    # Use the single strongest critical event, plus smaller corroborating events.
    critical_hits = []
    for phrase, pts, reason, cat, sc, impact in CRITICAL_RULES:
        if phrase in text:
            critical_hits.append((matched_points(phrase, pts), reason, cat, sc, impact))
    if critical_hits:
        critical_hits.sort(reverse=True, key=lambda x: x[0])
        strongest = critical_hits[0]
        score += strongest[0]
        reasons.append(strongest[1])
        category, scope = strongest[2], strongest[3]
        explicit_impacts.append(strongest[4])
        for extra in critical_hits[1:3]:
            score += min(8, extra[0] // 5)
            reasons.append(extra[1])

    macro_hits = []
    for phrase, pts, reason, cat, sc in MACRO_RULES:
        if phrase in text:
            macro_hits.append((matched_points(phrase, pts), reason, cat, sc))
    if macro_hits:
        macro_hits.sort(reverse=True, key=lambda x: x[0])
        strongest = macro_hits[0]
        score += strongest[0]
        reasons.append(strongest[1])
        if not critical_hits:
            category, scope = strongest[2], strongest[3]
        for extra in macro_hits[1:2]:
            score += min(7, extra[0] // 5)

    company_hits = []
    for phrase, pts, reason, cat, sc, impact in COMPANY_RULES:
        if phrase in text:
            company_hits.append((matched_points(phrase, pts), reason, cat, sc, impact))
    if company_hits:
        company_hits.sort(reverse=True, key=lambda x: x[0])
        strongest = company_hits[0]
        score += strongest[0]
        reasons.append(strongest[1])
        if not critical_hits and not macro_hits:
            category, scope = strongest[2], strongest[3]
        explicit_impacts.append(strongest[4])
        for extra in company_hits[1:2]:
            score += min(7, extra[0] // 5)

    for phrase, pts, reason in MARKET_STRESS:
        if phrase in text:
            score += matched_points(phrase, pts)
            reasons.append(reason)
            category = "Thị trường"
            scope = "Toàn thị trường" if "vn-index" in text or "thị trường" in text else scope
            break

    # Numbers often make an event more actionable; keep this a modest modifier.
    if re.search(r"(?:\d+[\.,]?\d*)\s*%", text):
        score += 4
        reasons.append("Có số liệu định lượng")
    if re.search(r"\b\d[\d\.,]*\s*(?:tỷ|triệu|nghìn tỷ)\b", text):
        score += 3

    # Hard-action modifiers: distinguish an actual decision/event from a generic mention.
    if any(p in title_n for p in [
        "tăng lãi suất điều hành", "giảm lãi suất điều hành",
        "nâng lãi suất điều hành", "hạ lãi suất điều hành",
        "fed tăng lãi suất", "fed giảm lãi suất", "fed hạ lãi suất",
    ]):
        score += 22
        reasons.append("Có quyết định/thay đổi chính sách trực tiếp")

    pct_values = []
    for m in re.finditer(r"(\d+(?:[\.,]\d+)?)\s*%", text):
        try:
            pct_values.append(float(m.group(1).replace(",", ".")))
        except Exception:
            pass
    if pct_values and max(pct_values) >= 30 and any(k in text for k in ["lợi nhuận", "doanh thu", "giảm", "tăng"]):
        score += 12
        reasons.append("Biến động định lượng lớn (≥30%)")

    if any(s in source_n for s in HIGH_AUTHORITY_SOURCES):
        score += 8
        reasons.append("Nguồn có độ tin cậy cao")

    # Pure opinion articles should rarely trigger email unless they also contain a hard event.
    if any(w in title_n for w in OPINION_WORDS) and not (critical_hits or company_hits or macro_hits):
        score -= 12
        reasons.append("Nội dung thiên về nhận định/dự báo")

    # Mentioning a tracked listed company makes the article more actionable.
    ticker_list = [str(t).strip().upper() for t in (tickers or []) if str(t).strip()]
    if ticker_list:
        score += min(7, 2 + len(ticker_list))

    if critical_hits and any(k in title_n for k in ["chủ tịch", "tổng giám đốc", "ceo", "cfo", "ban lãnh đạo"]):
        score += 8
        reasons.append("Liên quan trực tiếp lãnh đạo cấp cao")

    if explicit_impacts:
        # Prefer explicit negative/positive event rules; mixed if conflicts.
        unique = set(explicit_impacts)
        if len(unique) == 1:
            impact = explicit_impacts[0]
        elif "Negative" in unique and "Positive" in unique:
            impact = "Mixed"
        else:
            impact = next(iter(unique))
    else:
        p = sum(w in text for w in POSITIVE_HINTS)
        n = sum(w in text for w in NEGATIVE_HINTS)
        impact = "Positive" if p > n else "Negative" if n > p else "Neutral"

    if any(p in title_n for p in ["tăng lãi suất điều hành", "nâng lãi suất điều hành", "fed tăng lãi suất"]):
        impact = "Negative"
    elif any(p in title_n for p in ["giảm lãi suất điều hành", "hạ lãi suất điều hành", "fed giảm lãi suất", "fed hạ lãi suất"]):
        impact = "Positive"

    score = max(0, min(100, int(round(score))))
    if score >= 90:
        level = "CRITICAL"
    elif score >= 70:
        level = "HIGH"
    elif score >= 45:
        level = "MEDIUM"
    else:
        level = "LOW"

    # De-duplicate while preserving order.
    reasons = list(dict.fromkeys(reasons))[:4]
    if not reasons:
        reasons = ["Tin tài chính/thị trường mới được hệ thống ghi nhận"]

    return UrgencyResult(score, level, impact, category, scope, reasons).to_dict()


def urgency_badge(score: int) -> str:
    if score >= 90:
        return "🔴 CRITICAL"
    if score >= 70:
        return "🟠 HIGH"
    if score >= 45:
        return "🟡 MEDIUM"
    return "🟢 LOW"
