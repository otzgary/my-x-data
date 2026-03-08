"""
本地一次性脚本 — 把数据库里 100赞以上的主推文同步到 Sheet 1 (历史精华)。
运行方式: python sync_history.py
需要本地有 gary.db，且 .env 配置好。
"""

import sqlite3
from twitter_client import get_tweets_by_ids, normalize_tweet
from summarizer import summarize_batch
from sheets_client import write_history_sheet

DB_PATH = "/Users/gary/Documents/cc projects/数据库/gary.db"
MIN_LIKES = 100


def run():
    # 1. 从本地 DB 读取 100赞以上主推文的 ID
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "SELECT id FROM tweets WHERE is_reply = 0 AND favorite_count >= ? ORDER BY favorite_count DESC",
        (MIN_LIKES,),
    )
    tweet_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    print(f"本地 DB 中 {MIN_LIKES}赞+ 主推文: {len(tweet_ids)} 条")

    # 2. 从 twitterapi.io 批量拉取最新数据（含浏览量）
    print("从 twitterapi.io 拉取最新数据...")
    raw_tweets = get_tweets_by_ids(tweet_ids)
    print(f"API 返回 {len(raw_tweets)} 条")

    tweets = [normalize_tweet(t) for t in raw_tweets]

    # 3. LLM 概括推文内容
    print("LLM 概括中...")
    tweets = summarize_batch(tweets)

    # 4. 写入 Google Sheet
    write_history_sheet(tweets)
    print("历史精华 Sheet 同步完成！")


if __name__ == "__main__":
    run()
