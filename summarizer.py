import re
import httpx
from openai import OpenAI
from config import ANTHROPIC_API_KEY
import twitter_client as tc

# jiekou.ai 是国内服务，不需要走系统代理
_http_client = httpx.Client(proxy=None, timeout=30.0)
_client = OpenAI(
    api_key=ANTHROPIC_API_KEY,
    base_url="https://api.jiekou.ai/openai",
    http_client=_http_client,
)

# 用于解析 t.co 链接的独立 client（不走代理）
_fetch_client = httpx.Client(proxy=None, timeout=10.0, follow_redirects=True)


def _resolve_url(tco_url: str) -> str:
    """Follow t.co redirect to get the real URL."""
    try:
        resp = _fetch_client.head(tco_url)
        return str(resp.url)
    except Exception:
        return tco_url


def _fetch_page_title(url: str) -> str:
    """Fetch a webpage and extract its title and description."""
    try:
        resp = _fetch_client.get(url, headers={"Accept-Language": "zh-CN,zh;q=0.9"})
        html = resp.text[:5000]  # 只取前5000字符就够了

        # 提取 title
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ""

        # 提取 og:description
        desc_match = re.search(
            r'<meta[^>]+(?:name|property)=["\'](?:og:description|description)["\'][^>]+content=["\']([^"\']+)',
            html, re.IGNORECASE
        )
        if not desc_match:
            desc_match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:og:description|description)["\']',
                html, re.IGNORECASE
            )
        desc = desc_match.group(1).strip() if desc_match else ""

        parts = [p for p in [title, desc] if p]
        return " | ".join(parts[:2]) if parts else ""
    except Exception:
        return ""


def summarize_tweet(text: str, expanded_url: str = "", tweet_id: str = "", is_article: bool = False) -> str:
    """
    Summarize a tweet into one concise sentence.
    If the tweet text is just a t.co URL, tries to fetch the real page content.
    """
    clean = re.sub(r"https://t\.co/\S+", "", text).strip()

    # 纯文本，够短直接返回
    if clean and len(clean) <= 30:
        return clean

    context = clean

    # 如果推文正文基本是空的（纯链接推文），尝试获取链接内容
    if not clean or len(clean) < 10:
        # 优先：X Article 用 API 获取标题和预览
        if is_article and tweet_id:
            article_content = tc.get_article_content(tweet_id)
            if article_content:
                context = f"[X长文] {article_content}"
        # 其次：普通外链，抓页面 title
        if not context:
            tco_urls = re.findall(r"https://t\.co/\S+", text)
            if tco_urls:
                real_url = expanded_url or _resolve_url(tco_urls[0])
                if "x.com" not in real_url and "twitter.com" not in real_url:
                    page_info = _fetch_page_title(real_url)
                    if page_info:
                        context = f"[链接内容] {page_info}"

    if not context:
        return text.strip()

    response = _client.chat.completions.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": (
                    "请用一句话概括以下推文的核心内容。"
                    "要求：简洁直接，不超过30个字，用中文输出（如果原文是英文也用中文概括）。"
                    "只输出概括内容本身，不需要任何前缀或解释。\n\n"
                    f"推文内容：\n{context}"
                ),
            }
        ],
    )
    return response.choices[0].message.content.strip()


def summarize_batch(tweets: list[dict]) -> list[dict]:
    """Add 'summary' field to each tweet dict."""
    for tweet in tweets:
        tweet["summary"] = summarize_tweet(
            tweet["text"],
            expanded_url=tweet.get("expanded_url", ""),
            tweet_id=tweet.get("id", ""),
            is_article=tweet.get("is_article", False),
        )
    return tweets
