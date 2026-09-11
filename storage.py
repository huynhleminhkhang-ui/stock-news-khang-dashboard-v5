import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Iterable

import requests

BASE_DIR = Path(__file__).resolve().parent
LOCAL_DB = BASE_DIR / "data" / "alerts.db"


def _utc_now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _utc_now()).isoformat()


def url_hash(url: str, title: str = "") -> str:
    raw = (url or title or "").strip().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def supabase_enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL", "").strip() and os.getenv("SUPABASE_KEY", "").strip())


def backend_name() -> str:
    return "Supabase" if supabase_enabled() else "SQLite local"


def _sb_url(path: str) -> str:
    return os.getenv("SUPABASE_URL", "").rstrip("/") + "/rest/v1/" + path.lstrip("/")


def _sb_headers(prefer: str | None = None):
    key = os.getenv("SUPABASE_KEY", "").strip()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _ensure_local():
    LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(LOCAL_DB) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash TEXT UNIQUE NOT NULL,
            url TEXT,
            title TEXT NOT NULL,
            source TEXT,
            published_at TEXT,
            fetched_at TEXT,
            tickers TEXT,
            summary TEXT,
            news_type TEXT,
            urgency_score INTEGER DEFAULT 0,
            urgency_level TEXT,
            impact TEXT,
            market_scope TEXT,
            reasons TEXT,
            email_sent INTEGER DEFAULT 0,
            email_sent_at TEXT
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            email TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            urgency_threshold INTEGER DEFAULT 70,
            created_at TEXT
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS article_deliveries (
            article_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            PRIMARY KEY(article_id, email)
        )
        """)
        con.commit()


def save_article(article: dict):
    payload = {
        "url_hash": article.get("url_hash") or url_hash(article.get("url", ""), article.get("title", "")),
        "url": article.get("url", ""),
        "title": article.get("title", ""),
        "source": article.get("source", ""),
        "published_at": article.get("published_at") or article.get("published") or _iso(),
        "fetched_at": article.get("fetched_at") or _iso(),
        "tickers": article.get("tickers", []),
        "summary": article.get("summary", ""),
        "news_type": article.get("news_type", ""),
        "urgency_score": int(article.get("urgency_score", 0)),
        "urgency_level": article.get("urgency_level", "LOW"),
        "impact": article.get("impact", "Neutral"),
        "market_scope": article.get("market_scope", "Doanh nghiệp"),
        "reasons": article.get("reasons", []),
    }
    if supabase_enabled():
        r = requests.post(
            _sb_url("articles?on_conflict=url_hash"),
            headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
            json=payload,
            timeout=20,
        )
        r.raise_for_status()
        return

    _ensure_local()
    local = payload.copy()
    local["tickers"] = json.dumps(local["tickers"], ensure_ascii=False)
    local["reasons"] = json.dumps(local["reasons"], ensure_ascii=False)
    cols = list(local)
    placeholders = ",".join(["?"] * len(cols))
    updates = ",".join([f"{c}=excluded.{c}" for c in cols if c != "url_hash"])
    with sqlite3.connect(LOCAL_DB) as con:
        con.execute(
            f"INSERT INTO articles ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(url_hash) DO UPDATE SET {updates}",
            [local[c] for c in cols],
        )
        con.commit()


def _decode_local_row(row, columns):
    d = dict(zip(columns, row))
    for k in ("tickers", "reasons"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except Exception:
            d[k] = []
    d["email_sent"] = bool(d.get("email_sent"))
    return d


def get_recent_articles(limit: int = 100, min_score: int = 0):
    if supabase_enabled():
        params = {
            "select": "*",
            "urgency_score": f"gte.{int(min_score)}",
            "order": "published_at.desc",
            "limit": str(int(limit)),
        }
        r = requests.get(_sb_url("articles"), headers=_sb_headers(), params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    _ensure_local()
    with sqlite3.connect(LOCAL_DB) as con:
        cur = con.execute(
            "SELECT * FROM articles WHERE urgency_score >= ? ORDER BY published_at DESC LIMIT ?",
            (int(min_score), int(limit)),
        )
        cols = [x[0] for x in cur.description]
        return [_decode_local_row(row, cols) for row in cur.fetchall()]


def get_unsent_articles(min_score: int = 70, lookback_hours: int = 24):
    cutoff = (_utc_now() - timedelta(hours=lookback_hours)).isoformat()
    if supabase_enabled():
        params = {
            "select": "*",
            "email_sent": "eq.false",
            "urgency_score": f"gte.{int(min_score)}",
            "published_at": f"gte.{cutoff}",
            "order": "urgency_score.desc,published_at.desc",
        }
        r = requests.get(_sb_url("articles"), headers=_sb_headers(), params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    _ensure_local()
    with sqlite3.connect(LOCAL_DB) as con:
        cur = con.execute(
            "SELECT * FROM articles WHERE email_sent=0 AND urgency_score>=? AND published_at>=? "
            "ORDER BY urgency_score DESC, published_at DESC",
            (int(min_score), cutoff),
        )
        cols = [x[0] for x in cur.description]
        return [_decode_local_row(row, cols) for row in cur.fetchall()]


def mark_articles_sent(article_ids: Iterable):
    ids = [x for x in article_ids if x is not None]
    if not ids:
        return
    now = _iso()
    if supabase_enabled():
        # IDs are bigint in the supplied schema.
        id_list = ",".join(str(int(x)) for x in ids)
        r = requests.patch(
            _sb_url(f"articles?id=in.({id_list})"),
            headers=_sb_headers("return=minimal"),
            json={"email_sent": True, "email_sent_at": now},
            timeout=20,
        )
        r.raise_for_status()
        return

    _ensure_local()
    with sqlite3.connect(LOCAL_DB) as con:
        con.executemany(
            "UPDATE articles SET email_sent=1,email_sent_at=? WHERE id=?",
            [(now, int(x)) for x in ids],
        )
        con.commit()


def upsert_subscriber(email: str, urgency_threshold: int = 70, enabled: bool = True):
    email = (email or "").strip().lower()
    if not email:
        return
    payload = {
        "email": email,
        "enabled": bool(enabled),
        "urgency_threshold": int(urgency_threshold),
        "created_at": _iso(),
    }
    if supabase_enabled():
        r = requests.post(
            _sb_url("subscribers?on_conflict=email"),
            headers=_sb_headers("resolution=merge-duplicates,return=minimal"),
            json=payload,
            timeout=20,
        )
        r.raise_for_status()
        return
    _ensure_local()
    with sqlite3.connect(LOCAL_DB) as con:
        con.execute(
            "INSERT INTO subscribers(email,enabled,urgency_threshold,created_at) VALUES(?,?,?,?) "
            "ON CONFLICT(email) DO UPDATE SET enabled=excluded.enabled, urgency_threshold=excluded.urgency_threshold",
            (email, int(enabled), int(urgency_threshold), payload["created_at"]),
        )
        con.commit()


def disable_subscriber(email: str):
    email = (email or "").strip().lower()
    if not email:
        return
    if supabase_enabled():
        r = requests.patch(
            _sb_url("subscribers"), headers=_sb_headers("return=minimal"),
            params={"email": f"eq.{email}"}, json={"enabled": False}, timeout=20,
        )
        r.raise_for_status()
        return
    _ensure_local()
    with sqlite3.connect(LOCAL_DB) as con:
        con.execute("UPDATE subscribers SET enabled=0 WHERE email=?", (email,))
        con.commit()


def get_subscribers():
    emails = []
    if supabase_enabled():
        r = requests.get(
            _sb_url("subscribers"), headers=_sb_headers(),
            params={"select": "email,urgency_threshold,enabled", "enabled": "eq.true"}, timeout=20,
        )
        r.raise_for_status()
        rows = r.json()
    else:
        _ensure_local()
        with sqlite3.connect(LOCAL_DB) as con:
            rows = [
                {"email": r[0], "urgency_threshold": r[1], "enabled": bool(r[2])}
                for r in con.execute("SELECT email,urgency_threshold,enabled FROM subscribers WHERE enabled=1")
            ]

    extra = os.getenv("ALERT_RECIPIENTS", "")
    for raw in extra.split(","):
        e = raw.strip().lower()
        if e:
            emails.append({"email": e, "urgency_threshold": int(os.getenv("EMAIL_URGENCY_THRESHOLD", "70")), "enabled": True})

    seen = set()
    merged = []
    for r in rows + emails:
        e = (r.get("email") or "").strip().lower()
        if e and e not in seen:
            seen.add(e)
            merged.append(r)
    return merged


def get_delivered_article_ids(email: str, article_ids: Iterable):
    ids = [int(x) for x in article_ids if x is not None]
    if not ids:
        return set()
    email = (email or "").strip().lower()
    if supabase_enabled():
        id_list = ",".join(str(x) for x in ids)
        r = requests.get(
            _sb_url("article_deliveries"), headers=_sb_headers(),
            params={"select": "article_id", "email": f"eq.{email}", "article_id": f"in.({id_list})"}, timeout=20,
        )
        r.raise_for_status()
        return {int(x["article_id"]) for x in r.json()}
    _ensure_local()
    placeholders = ",".join(["?"] * len(ids))
    with sqlite3.connect(LOCAL_DB) as con:
        rows = con.execute(
            f"SELECT article_id FROM article_deliveries WHERE email=? AND article_id IN ({placeholders})",
            [email, *ids],
        ).fetchall()
    return {int(r[0]) for r in rows}


def record_deliveries(email: str, article_ids: Iterable):
    ids = [int(x) for x in article_ids if x is not None]
    if not ids:
        return
    email = (email or "").strip().lower()
    now = _iso()
    if supabase_enabled():
        payload = [{"article_id": x, "email": email, "sent_at": now} for x in ids]
        r = requests.post(
            _sb_url("article_deliveries?on_conflict=article_id,email"),
            headers=_sb_headers("resolution=ignore-duplicates,return=minimal"), json=payload, timeout=20,
        )
        r.raise_for_status()
        return
    _ensure_local()
    with sqlite3.connect(LOCAL_DB) as con:
        con.executemany(
            "INSERT OR IGNORE INTO article_deliveries(article_id,email,sent_at) VALUES(?,?,?)",
            [(x, email, now) for x in ids],
        )
        con.commit()


def stats_today():
    rows = get_recent_articles(limit=500, min_score=0)
    vn_tz = ZoneInfo("Asia/Ho_Chi_Minh")
    today = datetime.now(vn_tz).date()
    todays = []
    for r in rows:
        try:
            dt = datetime.fromisoformat(str(r.get("fetched_at", "")).replace("Z", "+00:00"))
            if dt.astimezone(vn_tz).date() == today:
                todays.append(r)
        except Exception:
            pass
    return {
        "scanned": len(todays),
        "urgent": sum(int(r.get("urgency_score", 0)) >= 70 for r in todays),
        "critical": sum(int(r.get("urgency_score", 0)) >= 90 for r in todays),
        "sent": sum(bool(r.get("email_sent")) for r in todays),
    }
