"""
Railway cron entry point — runs every 4 hours.
Updates Sheet 2 (近期动态) with tweets from the last 72 hours.
"""

from datetime import datetime, timezone, timedelta
from twitter_client import get_user_tweets_since, normalize_tweet
from summarizer import summarize_batch
from sheets_client import upsert_recent_sheet


def run():
    since = datetime.now(timezone.utc) - timedelta(hours=72)
    print(f"[{datetime.now(timezone.utc).isoformat()}] 拉取 72h 内推文，起点: {since.isoformat()}")

    raw_tweets = get_user_tweets_since(since)
    print(f"获取到 {len(raw_tweets)} 条主推文")

    if not raw_tweets:
        print("无新数据，退出")
        return

    tweets = [normalize_tweet(t) for t in raw_tweets]
    tweets = summarize_batch(tweets)
    upsert_recent_sheet(tweets)

    print("完成")


if __name__ == "__main__":
    run()
