import time
import requests
from datetime import datetime, timezone, timedelta
from config import TWITTER_API_KEY, TWITTER_USERNAME

BASE_URL = "https://api.twitterapi.io"
HEADERS = {"X-API-Key": TWITTER_API_KEY}

# Bypass system proxy for twitterapi.io
_session = requests.Session()
_session.trust_env = False  # ignore HTTP_PROXY / HTTPS_PROXY env vars


def _parse_created_at(s: str) -> datetime:
    """Parse Twitter's createdAt string to UTC datetime."""
    # twitterapi.io returns ISO format: "2025-09-10T17:59:11.000Z"
    # fallback for Twitter legacy format: "Wed Sep 10 17:59:11 +0000 2025"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    return dt.astimezone(timezone.utc)


def _is_main_tweet(tweet: dict) -> bool:
    """Return True if tweet is an original post (not a reply or retweet)."""
    if tweet.get("isReply"):
        return False
    if tweet.get("retweeted_tweet"):
        return False
    return True


def get_user_tweets_since(since_dt: datetime, username: str = TWITTER_USERNAME) -> list[dict]:
    """
    Fetch all main tweets posted after since_dt.
    Paginates until tweets are older than since_dt.
    """
    results = []
    cursor = ""
    page = 0

    while True:
        params = {"userName": username, "includeReplies": "false"}
        if cursor:
            params["cursor"] = cursor

        resp = _session.get(f"{BASE_URL}/twitter/user/last_tweets", headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()

        tweets = data.get("data", {}).get("tweets", [])
        if not tweets:
            break

        reached_cutoff = False
        for tweet in tweets:
            created_at = _parse_created_at(tweet["createdAt"])
            if created_at < since_dt:
                reached_cutoff = True
                break
            if _is_main_tweet(tweet):
                results.append(tweet)

        page += 1
        if reached_cutoff or not data.get("has_next_page"):
            break

        cursor = data.get("next_cursor", "")
        time.sleep(0.3)  # be gentle

    return results


def get_article_content(tweet_id: str) -> str:
    """Fetch X Article content for a tweet that links to an article."""
    try:
        resp = _session.get(f"{BASE_URL}/twitter/article", headers=HEADERS, params={"tweet_id": tweet_id})
        resp.raise_for_status()
        article = resp.json().get("article", {})
        title = article.get("title", "")
        contents = article.get("contents", [])
        body = " ".join(c.get("text", "") for c in contents if c.get("text"))
        parts = [p for p in [title, body[:1500]] if p]
        return "\n".join(parts)
    except Exception:
        return ""


def get_tweets_by_ids(tweet_ids: list[str]) -> list[dict]:
    """
    Fetch tweet data for a list of tweet IDs.
    twitterapi.io supports batch: /twitter/tweets?tweet_ids=id1,id2,...
    Processes in chunks of 100.
    """
    results = []
    chunk_size = 100

    for i in range(0, len(tweet_ids), chunk_size):
        chunk = tweet_ids[i : i + chunk_size]
        params = {"tweet_ids": ",".join(chunk)}

        resp = _session.get(f"{BASE_URL}/twitter/tweets", headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()

        # Response may be {"tweets": [...]} or {"data": [...]}
        tweets = data.get("tweets") or data.get("data") or []
        results.extend(tweets)
        time.sleep(0.3)

    return results


def normalize_tweet(tweet: dict) -> dict:
    """Normalize API response to a flat dict with consistent field names."""
    # Extract first expanded URL from entities (for URL-only tweets)
    expanded_url = ""
    entities = tweet.get("entities") or {}
    urls = entities.get("urls") or []
    if urls and isinstance(urls, list):
        expanded_url = urls[0].get("expanded_url") or urls[0].get("url") or ""

    # Check if this is an X Article (x.com/i/article/...)
    is_article = "x.com/i/article" in expanded_url or "twitter.com/i/article" in expanded_url

    return {
        "id": tweet.get("id", ""),
        "created_at": tweet.get("createdAt", ""),
        "text": tweet.get("text", ""),
        "url": tweet.get("url", ""),
        "expanded_url": expanded_url,
        "is_article": is_article,
        "view_count": tweet.get("viewCount", 0) or 0,
        "like_count": tweet.get("likeCount", 0) or 0,
        "retweet_count": tweet.get("retweetCount", 0) or 0,
        "reply_count": tweet.get("replyCount", 0) or 0,
        "quote_count": tweet.get("quoteCount", 0) or 0,
        "bookmark_count": tweet.get("bookmarkCount", 0) or 0,
    }
