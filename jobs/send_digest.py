import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from email_service import send_digest
from storage import (
    get_delivered_article_ids, get_recent_articles, get_subscribers,
    mark_articles_sent, record_deliveries,
)


def main():
    subscribers = get_subscribers()
    if not subscribers:
        print("No enabled subscribers; nothing sent.")
        return

    lookback_hours = int(os.getenv("EMAIL_LOOKBACK_HOURS", "24"))
    # The DB list is already newest first. Background refresh runs every 20 minutes.
    # Limit is intentionally generous; per-recipient dedupe happens below.
    articles = get_recent_articles(limit=500, min_score=min(int(s.get("urgency_threshold", 70)) for s in subscribers))
    if not articles:
        print("No urgent articles; nothing sent.")
        return

    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    fresh = []
    for a in articles:
        try:
            dt = datetime.fromisoformat(str(a.get("published_at", "")).replace("Z", "+00:00"))
            if dt >= cutoff:
                fresh.append(a)
        except Exception:
            fresh.append(a)

    any_sent_ids = set()
    max_articles = int(os.getenv("EMAIL_MAX_ARTICLES", "20"))
    for sub in subscribers:
        email = sub["email"]
        threshold = int(sub.get("urgency_threshold", 70))
        eligible = [a for a in fresh if int(a.get("urgency_score", 0)) >= threshold]
        delivered = get_delivered_article_ids(email, [a.get("id") for a in eligible])
        selected = [a for a in eligible if a.get("id") is None or int(a["id"]) not in delivered][:max_articles]
        if not selected:
            print(f"No new qualifying articles for {email}")
            continue
        send_digest(email, selected)
        ids = [a.get("id") for a in selected if a.get("id") is not None]
        record_deliveries(email, ids)
        any_sent_ids.update(ids)
        print(f"Sent {len(selected)} articles to {email}")

    # Retained for dashboard-wide status only; per-recipient dedupe uses article_deliveries.
    if any_sent_ids:
        mark_articles_sent(any_sent_ids)


if __name__ == "__main__":
    main()
