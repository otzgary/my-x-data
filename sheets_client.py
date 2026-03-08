import json
import gspread
from datetime import datetime, timezone, timedelta
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession
from config import GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

COLUMNS = [
    "发布时间", "内容摘要", "原文",
    "浏览量", "点赞", "转发", "引用", "回复", "书签", "链接",
]

# Column indices (0-based)
COL_DATE    = 0
COL_SUMMARY = 1
COL_TEXT    = 2
COL_VIEWS   = 3
COL_LIKES   = 4
COL_RT      = 5
COL_QUOTE   = 6
COL_REPLY   = 7
COL_BM      = 8
COL_URL     = 9

HISTORY_SHEET = "历史精华 (100赞+)"
RECENT_SHEET  = "近期动态 (72h)"

CST = timezone(timedelta(hours=8))


def _get_client() -> gspread.Client:
    creds_info = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_worksheet(spreadsheet: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=2000, cols=len(COLUMNS))
    return ws


def _ensure_header(ws: gspread.Worksheet):
    existing = ws.row_values(1)
    if existing != COLUMNS:
        ws.update("A1", [COLUMNS])
        ws.format("A1:J1", {"textFormat": {"bold": True}})


def _format_date(created_at: str) -> str:
    """Convert API date string to Beijing time: '2026-03-08 22:21'"""
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            return created_at
    return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M")


def _tweet_to_row(tweet: dict) -> list:
    return [
        _format_date(tweet.get("created_at", "")),
        tweet.get("summary", ""),
        tweet.get("text", ""),
        tweet.get("view_count", 0),
        tweet.get("like_count", 0),
        tweet.get("retweet_count", 0),
        tweet.get("quote_count", 0),
        tweet.get("reply_count", 0),
        tweet.get("bookmark_count", 0),
        tweet.get("url", ""),
    ]


def write_history_sheet(tweets: list[dict]):
    """Write (or overwrite) the history sheet. Sorted by like_count descending."""
    client = _get_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    ws = _get_or_create_worksheet(spreadsheet, HISTORY_SHEET)
    _ensure_header(ws)

    sorted_tweets = sorted(tweets, key=lambda t: t.get("like_count", 0), reverse=True)
    rows = [_tweet_to_row(t) for t in sorted_tweets]

    if rows:
        ws.resize(rows=len(rows) + 1)
        ws.update(f"A2:J{len(rows) + 1}", rows)

    print(f"[历史精华] 写入 {len(rows)} 条推文")


def upsert_recent_sheet(tweets: list[dict]):
    """
    Upsert tweets into the recent sheet using URL as the unique key.
    - New tweets: append (with summary)
    - Existing tweets: update metrics only (preserve existing summary)
    - Tweets not in incoming list (older than 72h): removed
    """
    client = _get_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    ws = _get_or_create_worksheet(spreadsheet, RECENT_SHEET)
    _ensure_header(ws)

    all_values = ws.get_all_values()
    existing_rows = all_values[1:] if len(all_values) > 1 else []

    # Index existing rows by URL
    existing_by_url: dict[str, list] = {}
    for row in existing_rows:
        if len(row) > COL_URL and row[COL_URL]:
            existing_by_url[row[COL_URL]] = row

    incoming_by_url = {t["url"]: t for t in tweets}

    final_rows = []
    seen_urls = set()

    # Update existing rows that are still in the 72h window
    for url, row in existing_by_url.items():
        if url in incoming_by_url:
            tweet = incoming_by_url[url]
            updated = list(row) + [""] * (len(COLUMNS) - len(row))  # pad if short
            updated[COL_VIEWS] = tweet.get("view_count", 0)
            updated[COL_LIKES] = tweet.get("like_count", 0)
            updated[COL_RT]    = tweet.get("retweet_count", 0)
            updated[COL_QUOTE] = tweet.get("quote_count", 0)
            updated[COL_REPLY] = tweet.get("reply_count", 0)
            updated[COL_BM]    = tweet.get("bookmark_count", 0)
            final_rows.append(updated)
            seen_urls.add(url)

    # Append new tweets
    new_tweets = [t for t in tweets if t["url"] not in seen_urls]
    for tweet in new_tweets:
        final_rows.append(_tweet_to_row(tweet))

    # Sort by date descending (newest first)
    final_rows.sort(key=lambda r: r[COL_DATE], reverse=True)

    # Rewrite sheet
    ws.resize(rows=max(len(final_rows) + 1, 2))
    if final_rows:
        ws.update(f"A2:J{len(final_rows) + 1}", final_rows)
    total_rows = ws.row_count
    if total_rows > len(final_rows) + 1:
        ws.batch_clear([f"A{len(final_rows) + 2}:J{total_rows}"])

    print(f"[近期动态] 保留 {len(final_rows)} 条（新增 {len(new_tweets)} 条，更新 {len(seen_urls)} 条）")
