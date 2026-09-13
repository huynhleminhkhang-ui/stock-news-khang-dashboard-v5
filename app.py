import os
import re
import html
import calendar
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from analysis_engine import classify_region, detect_sector, extract_tickers, investment_thesis, market_synthesis
from urgency import calculate_urgency, urgency_badge
from storage import (
    backend_name, disable_subscriber, get_recent_articles, stats_today,
    upsert_subscriber, supabase_enabled,
)

load_dotenv()
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

st.set_page_config(page_title="Market Intelligence V5.1", page_icon="📈", layout="wide")

st.markdown("""
<style>
.block-container {padding-top:1.2rem;padding-bottom:2rem;}
[data-testid="stSidebar"] {background:#f8fafc!important;border-right:1px solid #e2e8f0!important;}
html, body, [data-testid="stAppViewContainer"], .stApp {background:#fff!important;color:#0f172a!important;}
[data-testid="stHeader"] {background:rgba(255,255,255,.96)!important;}
.dashboard-title {font-size:2.1rem;font-weight:800;margin-bottom:.2rem;color:#0f172a!important;}
.dashboard-sub,.small-muted {color:#64748b!important;}
.metric-card,.summary-box,.thesis-box,.alert-panel {background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:16px 18px;box-shadow:0 2px 10px rgba(15,23,42,.04);}
.market-box {background:#eff6ff;border:1px solid #bfdbfe;border-radius:16px;padding:16px 18px;color:#1e3a8a;}
.risk-box {background:#fef2f2;border:1px solid #fecaca;border-radius:14px;padding:14px 16px;}
.opportunity-box {background:#f0fdf4;border:1px solid #bbf7d0;border-radius:14px;padding:14px 16px;}
.urgency-critical {background:#fef2f2;border:1px solid #fecaca;border-radius:12px;padding:12px 14px;}
.urgency-high {background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:12px 14px;}
.quick-view {background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:12px 14px;}
[data-testid="stMetric"] {background:#fff!important;border:1px solid #e2e8f0!important;border-radius:14px!important;padding:12px 14px!important;}
[data-testid="stExpander"] {background:#fff!important;border:1px solid #e2e8f0!important;border-radius:14px!important;}
.stButton>button[kind="primary"] {background:#2563eb!important;color:#fff!important;border-color:#2563eb!important;}
</style>
""", unsafe_allow_html=True)

COMPANY_NAMES = {
    "FPT":"CTCP FPT","SSI":"Chứng khoán SSI","VIC":"Vingroup","VHM":"Vinhomes",
    "VCB":"Vietcombank","BID":"BIDV","CTG":"VietinBank","TCB":"Techcombank",
    "MBB":"MB Bank","VPB":"VPBank","HPG":"Hòa Phát","MWG":"Thế Giới Di Động",
    "VNM":"Vinamilk","GAS":"PV GAS","PLX":"Petrolimex","VND":"VNDirect",
    "HCM":"HSC","STB":"Sacombank","ACB":"ACB","TPB":"TPBank","PVS":"PVS",
    "MSN":"Masan","VRE":"Vincom Retail","GVR":"Cao su Việt Nam","POW":"PV Power",
    "DGC":"Hóa chất Đức Giang","SAB":"Sabeco","SHB":"SHB"
}


def clean_text(raw: str) -> str:
    if not raw: return ""
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def normalize_title(title: str) -> str:
    title = re.sub(r"\s+-\s+[^-]+$", "", (title or "").lower())
    title = re.sub(r"[^0-9a-zA-ZÀ-ỹ\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def parsed_entry_time(entry):
    if entry.get("published_parsed"):
        return datetime.fromtimestamp(calendar.timegm(entry.published_parsed), tz=timezone.utc)
    if entry.get("updated_parsed"):
        return datetime.fromtimestamp(calendar.timegm(entry.updated_parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_google_news(ticker: str, days: int = 7, max_items: int = 20):
    ticker = ticker.strip().upper()
    company = COMPANY_NAMES.get(ticker, ticker)
    query = f'"{ticker}" "{company}" (cổ phiếu OR chứng khoán OR doanh nghiệp) when:{days}d'
    url = "https://news.google.com/rss/search?" + f"q={quote_plus(query)}&hl=vi&gl=VN&ceid=VN:vi"
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows, seen = [], set()
    for entry in feed.entries:
        published = parsed_entry_time(entry)
        if published < cutoff: continue
        title = clean_text(entry.get("title", "")); summary = clean_text(entry.get("summary", ""))
        combined = f"{title} {summary}".upper()
        if ticker not in combined and company.upper() not in combined: continue
        key = normalize_title(title)
        if not key or key in seen: continue
        seen.add(key)
        src = entry.get("source"); source = src.get("title", "") if isinstance(src, dict) else "Google News"
        rows.append({
            "ticker":ticker,"tickers":[ticker],"title":title,"summary":summary,"source":source or "Google News",
            "url":entry.get("link", ""),"published_dt":published,"published_at":published.isoformat(),
            "published":published.astimezone().strftime("%d/%m/%Y %H:%M"),"date":published.astimezone().strftime("%d/%m/%Y"),
            "region":"Việt Nam","market_topic":detect_sector(combined),
        })
        if len(rows) >= max_items: break
    rows.sort(key=lambda x:x["published_dt"], reverse=True)
    return rows


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_article_text(url: str) -> str:
    if not url: return ""
    try:
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        if r.status_code != 200: return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script","style","noscript","header","footer","nav","aside"]): tag.decompose()
        candidates=[]
        for selector in ["article",".article-content",".detail-content",".fck_detail",".entry-content",".post-content",".content"]:
            for node in soup.select(selector):
                text=clean_text(node.get_text(" ",strip=True))
                if len(text)>500: candidates.append(text)
        if candidates: return max(candidates,key=len)[:12000]
        paras=[clean_text(p.get_text(" ",strip=True)) for p in soup.find_all("p")]
        return " ".join(x for x in paras if len(x)>40)[:12000]
    except Exception:
        return ""


def classify_news(text: str) -> str:
    s=(text or "").lower()
    if any(k in s for k in ["khởi tố","đình chỉ giao dịch","hủy niêm yết","thanh tra","kiểm toán"]): return "Pháp lý / Quản trị"
    if any(k in s for k in ["lãi suất","tỷ giá","fed","gdp","cpi","lạm phát","nhnn","thuế quan"]): return "Vĩ mô / Chính sách"
    if any(k in s for k in ["vn-index","s&p 500","nasdaq","dow jones","hang seng","nikkei"]): return "Thị trường"
    if any(k in s for k in ["lợi nhuận","doanh thu","cổ tức","phát hành","m&a","sáp nhập"]): return "Doanh nghiệp"
    return "Ngành / Doanh nghiệp"


def fallback_summary(item, article_text=""):
    source=clean_text(article_text or item.get("summary","") or item.get("title",""))
    title=clean_text(item.get("title",""))
    sentences=re.split(r'(?<=[.!?])\s+', source)
    numeric=[s for s in sentences if re.search(r"\d",s)]
    other=[s for s in sentences if s not in numeric]
    chosen=[clean_text(x) for x in (numeric+other)[:5] if len(clean_text(x))>25] or [title]
    return chosen[:4]


def ai_summary(item, article_text, model):
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key or OpenAI is None: return None
    client=OpenAI(api_key=key)
    evidence=article_text or item.get("summary","")
    resp=client.responses.create(
        model=model,
        instructions=("Bạn là trợ lý phân tích tin chứng khoán. Chỉ dùng dữ liệu được cung cấp. "
                      "Tóm tắt 4-6 bullet có số liệu, nêu catalyst, rủi ro và tác động đến doanh nghiệp/ngành. "
                      "Không bịa dữ liệu và không đưa khuyến nghị mua/bán."),
        input=f"Mã: {item.get('ticker','')}\nTiêu đề: {item.get('title','')}\nNguồn: {item.get('source','')}\nNội dung:\n{evidence[:12000]}"
    )
    return resp.output_text.strip()


def merge_articles(rows, watched):
    grouped={}
    for item in rows:
        key=item.get("url") or normalize_title(item.get("title",""))
        if key not in grouped: grouped[key]={**item,"tickers":set(item.get("tickers",[]))}
        grouped[key]["tickers"].add(item["ticker"])
        combined=f"{item.get('title','')} {item.get('summary','')}"
        grouped[key]["tickers"].update(extract_tickers(combined))
        for t in watched:
            if re.search(rf"(?<![A-Z0-9]){re.escape(t)}(?![A-Z0-9])", combined.upper()): grouped[key]["tickers"].add(t)
    out=list(grouped.values())
    out.sort(key=lambda x:x["published_dt"], reverse=True)
    return out


def process_article(item,use_ai=False,model="gpt-5.6"):
    text=fetch_article_text(item.get("url","")); item["article_text"]=text
    if use_ai:
        try: item["ai_detail"]=ai_summary(item,text,model)
        except Exception: item["ai_detail"]=None
    combined=f"{item.get('title','')} {item.get('summary','')} {text}"
    item["market_topic"]=detect_sector(combined); item["region"]=classify_region(combined,item.get("region",""))
    return item


def row_for_table(item):
    bullets=fallback_summary(item,item.get("article_text","")); summary=" ".join(bullets[:2])[:360]
    urg=calculate_urgency(item.get("title",""),item.get("summary",""),item.get("source",""),item.get("tickers",[]))
    return {
        "Ngày":item.get("date") or str(item.get("published_at", ""))[:10],
        "Mã CK":", ".join(sorted(item.get("tickers",[]))) or "Market",
        "Urgency":urg["score"],"Mức độ":urgency_badge(urg["score"]),"Tóm tắt":summary,
        "Impact":urg["impact"],"Ngành/Chủ đề":item.get("market_topic") or detect_sector(f"{item.get('title','')} {item.get('summary','')}"),
        "Nguồn":item.get("source",""),"Đọc tin gốc":item.get("url","")
    }


def filter_by_days(rows,days):
    cutoff=datetime.now(timezone.utc)-timedelta(days=days); out=[]
    for a in rows:
        try:
            dt=datetime.fromisoformat(str(a.get("published_at","")).replace("Z","+00:00"))
            if dt>=cutoff: out.append(a)
        except Exception: out.append(a)
    return out


def render_market_synthesis(rows,title="🌐 Tổng kết thị trường, ngành & kinh tế"):
    synth=market_synthesis(rows)
    st.markdown(f"### {title}")
    st.markdown(f'<div class="market-box"><b>Trạng thái chung: {synth["tone"]}</b><br>{synth["headline"]}</div>', unsafe_allow_html=True)
    for b in synth.get("bullets",[]): st.markdown(f"- {b}")
    c1,c2=st.columns(2)
    with c1:
        st.markdown("**📈 Catalyst / tín hiệu tích cực nổi bật**")
        if synth["opportunities"]:
            for x in synth["opportunities"]: st.markdown(f"- {x}")
        else: st.caption("Chưa có catalyst rõ ràng trong tập tin hiện tại.")
    with c2:
        st.markdown("**⚠️ Rủi ro nổi bật**")
        if synth["risks"]:
            for x in synth["risks"]: st.markdown(f"- {x}")
        else: st.caption("Chưa có rủi ro nổi bật trong tập tin hiện tại.")


st.markdown('<div class="dashboard-title">📈 Market Intelligence V5.1</div>',unsafe_allow_html=True)
st.markdown('<div class="dashboard-sub">News intelligence · Investment thesis · Broad-market urgency alerts</div>',unsafe_allow_html=True)

tab_news,tab_thesis,tab_alerts=st.tabs(["📰 Market Intelligence","🎯 Investment Thesis","🔔 Alerts & Urgency"])

with tab_news:
    try: market_rows=get_recent_articles(limit=220,min_score=0)
    except Exception: market_rows=[]
    if market_rows:
        render_market_synthesis(market_rows)
    else:
        st.info("Chưa có dữ liệu thị trường nền. Sau khi cấu hình Supabase, chạy workflow **Update Financial News** để nạp tin toàn thị trường.")

    st.divider(); st.markdown("### 🔎 Phân tích sâu theo mã cổ phiếu")
    with st.sidebar:
        st.header("Market Intelligence")
        ticker_text=st.text_input("Mã cổ phiếu cần phân tích",value="FPT, TCB, VIC, VHM, PVS",placeholder="VD: FPT, SSI, VCB")
        days=st.selectbox("Khoảng tin",[1,3,7,14,30],index=2)
        max_items=st.slider("Số bài tối đa / mã",5,30,12)
        use_ai=st.toggle("Dùng AI để tóm tắt sâu",value=False)
        model=st.text_input("OpenAI model",value=os.getenv("OPENAI_MODEL","gpt-5.6"),disabled=not use_ai)
        run=st.button("🔎 Quét và phân tích",type="primary",use_container_width=True)
    tickers=[]
    for part in ticker_text.split(","):
        t=part.strip().upper()
        if t and t not in tickers: tickers.append(t)
    if "merged_news" not in st.session_state: st.session_state.merged_news=[]
    if run and tickers:
        all_news=[]
        with st.spinner("Đang lấy và đọc tin..."):
            for t in tickers: all_news.extend(fetch_google_news(t,days,max_items))
            merged=merge_articles(all_news,tickers)
            processed=[]; prog=st.progress(0)
            for i,item in enumerate(merged):
                processed.append(process_article(item,use_ai,model)); prog.progress((i+1)/max(1,len(merged)))
            prog.empty(); st.session_state.merged_news=processed
    merged=st.session_state.merged_news
    if merged:
        render_market_synthesis(merged,"🧭 Tổng kết riêng cho các mã đang phân tích")
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Tin đã quét",len(merged)); c2.metric("Mã theo dõi",len(tickers)); c3.metric("HIGH/CRITICAL",sum(calculate_urgency(x.get('title',''),x.get('summary',''),x.get('source',''),x.get('tickers',[]))["score"]>=70 for x in merged)); c4.metric("Nguồn báo",len(set(x.get("source","") for x in merged)))
        df=pd.DataFrame([row_for_table(x) for x in merged])
        st.dataframe(df,hide_index=True,use_container_width=True,column_config={"Urgency":st.column_config.ProgressColumn("Urgency",min_value=0,max_value=100),"Đọc tin gốc":st.column_config.LinkColumn("Đọc tin gốc",display_text="Mở bài ↗")})
        st.download_button("⬇️ Tải bảng tin CSV",data=df.to_csv(index=False).encode("utf-8-sig"),file_name="market_intelligence_v51.csv",mime="text/csv")
        st.markdown("### 🔎 Chi tiết từng tin")
        for i,item in enumerate(merged,1):
            urg=calculate_urgency(item.get("title",""),item.get("summary",""),item.get("source",""),item.get("tickers",[])); bullets=fallback_summary(item,item.get("article_text",""))
            with st.expander(f"{i}. [{', '.join(sorted(item.get('tickers',[]))) or 'Market'}] {item.get('title','')}",expanded=(i==1)):
                a,b,c,d=st.columns(4); a.write(f"**📅 {item.get('published','')}**"); b.write(f"**🏷 {classify_news(item.get('title','')+' '+item.get('summary',''))}**"); c.write(f"**{item.get('market_topic','')}**"); d.write(f"**🔗 {item.get('source','')}**")
                cls="urgency-critical" if urg["score"]>=90 else "urgency-high" if urg["score"]>=70 else "quick-view"
                st.markdown(f'<div class="{cls}"><b>⚡ {urgency_badge(urg["score"])} · {urg["score"]}/100</b><br><span class="small-muted">Impact: {urg["impact"]} · Scope: {urg["market_scope"]} · {" · ".join(urg["reasons"])}</span></div>',unsafe_allow_html=True)
                st.markdown("**Tóm tắt chi tiết:**")
                if item.get("ai_detail"): st.markdown(item["ai_detail"])
                else:
                    for bullet in bullets: st.markdown(f"- {bullet}")
                if item.get("url"): st.link_button("📰 Đọc tin gốc",item["url"])
    else:
        st.info("Nhập mã và nhấn **Quét và phân tích** để xem phân tích chuyên sâu theo cổ phiếu.")

with tab_thesis:
    st.markdown("### 🎯 Investment Thesis từ news flow")
    st.caption("Thay thế Bond Valuation của V5. Tab này gom nhiều bài báo của cùng một mã để hình thành bull case, bear case, catalyst và risk. Không phải định giá mục tiêu.")
    try: thesis_db=get_recent_articles(limit=500,min_score=0)
    except Exception: thesis_db=[]
    combined=list(thesis_db)
    known={a.get("url") for a in combined}
    for x in st.session_state.get("merged_news",[]):
        if x.get("url") not in known:
            urg=calculate_urgency(x.get("title",""),x.get("summary",""),x.get("source",""),x.get("tickers",[]))
            combined.append({**x,"urgency_score":urg["score"],"urgency_level":urg["level"],"impact":urg["impact"],"market_scope":urg["market_scope"],"reasons":urg["reasons"]})
    t1,t2=st.columns([1.4,1])
    ticker_thesis=t1.text_input("Mã cổ phiếu",value="FPT",key="thesis_ticker").strip().upper()
    thesis_days=t2.selectbox("News lookback",[3,7,14,30],index=1,key="thesis_days")
    scoped=filter_by_days(combined,thesis_days)
    thesis=investment_thesis(ticker_thesis,scoped)
    m1,m2,m3=st.columns(3); m1.metric("Quan điểm news-flow",thesis["stance"]); m2.metric("Độ tin cậy",thesis["confidence"]); m3.metric("Số bài bằng chứng",thesis["evidence_count"])
    st.markdown(f'<div class="thesis-box">{thesis["summary"]}</div>',unsafe_allow_html=True)
    c1,c2=st.columns(2)
    with c1:
        st.markdown("#### 📈 Bull case")
        if thesis["bull"]:
            for x in thesis["bull"]: st.markdown(f"- {x}")
        else: st.caption("Chưa có luận cứ tích cực đủ rõ.")
        st.markdown("#### 🚀 Catalyst")
        for x in thesis["catalysts"] or ["Chưa có catalyst rõ ràng trong news flow."]: st.markdown(f"- {x}")
    with c2:
        st.markdown("#### 📉 Bear case")
        if thesis["bear"]:
            for x in thesis["bear"]: st.markdown(f"- {x}")
        else: st.caption("Chưa có luận cứ tiêu cực đủ rõ.")
        st.markdown("#### ⚠️ Risk")
        for x in thesis["risks"] or ["Chưa có risk headline nổi bật trong news flow."]: st.markdown(f"- {x}")
    st.info("Cách dùng: coi đây là lớp **news/catalyst thesis**. Trước quyết định đầu tư vẫn nên đối chiếu định giá, BCTC, dòng tiền và mức chịu rủi ro của chính bạn.")

with tab_alerts:
    st.markdown("### 🔔 Broad-Market Alerts & Urgency")
    st.caption("V5.1 quét rộng thị trường Việt Nam, doanh nghiệp niêm yết, ngành, vĩ mô và các biến số quốc tế có thể tác động tới chứng khoán. Không còn phụ thuộc danh sách WATCH_TICKERS.")
    try: stats=stats_today()
    except Exception as exc:
        stats={"scanned":0,"urgent":0,"critical":0,"sent":0}; st.warning(f"Chưa đọc được kho alert: {exc}")
    a,b,c,d=st.columns(4); a.metric("Tin đã quét hôm nay",stats["scanned"]); b.metric("Urgent ≥70",stats["urgent"]); c.metric("Critical ≥90",stats["critical"]); d.metric("Tin đã gửi",stats["sent"])
    st.markdown(f'<div class="alert-panel"><b>System:</b> 🟢 Ready &nbsp; | &nbsp; <b>Storage:</b> {backend_name()} &nbsp; | &nbsp; <b>Scan:</b> 20 phút &nbsp; | &nbsp; <b>Delivery:</b> 07:00 · 09:00 · 12:00 · 17:00 &nbsp; | &nbsp; <b>Email:</b> Resend API</div>',unsafe_allow_html=True)
    st.markdown("#### 📬 Cấu hình nhận Market Digest")
    c1,c2=st.columns([2.2,1]); alert_email=c1.text_input("Email nhận digest",placeholder="yourname@gmail.com",key="alert_email"); threshold=c2.slider("Minimum urgency",50,95,70,5,key="alert_threshold")
    b1,b2=st.columns(2)
    if b1.button("✅ Bật / cập nhật email alerts",type="primary",use_container_width=True):
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$",alert_email or ""): st.error("Email chưa đúng định dạng.")
        else:
            try: upsert_subscriber(alert_email,threshold,True); st.success(f"Đã bật alerts cho {alert_email}, ngưỡng {threshold}/100.")
            except Exception as exc: st.error(f"Không lưu được cấu hình: {exc}")
    if b2.button("🔕 Tắt alerts",use_container_width=True):
        try: disable_subscriber(alert_email); st.success("Đã tắt alerts cho email này.")
        except Exception as exc: st.error(f"Không cập nhật được: {exc}")
    if not supabase_enabled(): st.info("App đang dùng SQLite local. Khi deploy production, thêm SUPABASE_URL và SUPABASE_KEY để Streamlit và GitHub Actions dùng chung database.")

    st.markdown("#### ⚡ News radar")
    f1,f2,f3=st.columns(3)
    alert_filter=f1.selectbox("Mức urgency",["HIGH + CRITICAL","CRITICAL only","Tất cả"],index=0)
    region_filter=f2.selectbox("Khu vực",["Tất cả","Việt Nam","Quốc tế"],index=0)
    topic_filter=f3.selectbox("Chủ đề",["Tất cả","Ngân hàng","Bất động sản","Chứng khoán","Thép / Vật liệu","Dầu khí / Năng lượng","Công nghệ","Bán lẻ / Tiêu dùng","Xuất khẩu","Logistics / Hàng không","Đa ngành / Thị trường"],index=0)
    min_score=70 if alert_filter=="HIGH + CRITICAL" else 90 if alert_filter=="CRITICAL only" else 0
    try: recent=get_recent_articles(limit=180,min_score=min_score)
    except Exception as exc: recent=[]; st.error(f"Không tải được alerts: {exc}")
    if region_filter!="Tất cả": recent=[x for x in recent if (x.get("region") or classify_region(f"{x.get('title','')} {x.get('summary','')}"))==region_filter]
    if topic_filter!="Tất cả": recent=[x for x in recent if (x.get("market_topic") or detect_sector(f"{x.get('title','')} {x.get('summary','')}"))==topic_filter]
    if recent:
        render_market_synthesis(recent,"🧠 Tổng hợp nhanh từ News Radar")
        rows=[]
        for x in recent:
            t=x.get("tickers") or []; t=[t] if isinstance(t,str) else t
            rows.append({"Urgency":int(x.get("urgency_score",0)),"Mức độ":urgency_badge(int(x.get("urgency_score",0))),"Khu vực":x.get("region",""),"Mã CK":", ".join(t) or "Market","Tiêu đề":x.get("title",""),"Impact":x.get("impact",""),"Chủ đề":x.get("market_topic",""),"Nguồn":x.get("source",""),"Link":x.get("url","")})
        rdf=pd.DataFrame(rows)
        st.dataframe(rdf,hide_index=True,use_container_width=True,column_config={"Urgency":st.column_config.ProgressColumn("Urgency",min_value=0,max_value=100),"Link":st.column_config.LinkColumn("Link",display_text="Mở ↗")})
    else:
        st.info("Chưa có dữ liệu phù hợp. Chạy workflow **Update Financial News** một lần để nạp broad-market feed.")

st.caption("⚠️ V5.1 là công cụ tổng hợp và sàng lọc thông tin. Investment Thesis phản ánh news flow/catalyst, không phải khuyến nghị mua/bán hoặc định giá mục tiêu.")
