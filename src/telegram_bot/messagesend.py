import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN    = os.getenv("BOT_TOKEN")
CHAT_ID      = os.getenv("CHAT_ID")
ARCHIVE_PATH = "src/data/published_news.json"

TELEGRAM_API  = f"https://api.telegram.org/bot{BOT_TOKEN}"

SEND_DELAY    = 4
MAX_RETRIES   = 4
BACKOFF_BASE  = 5


def _make_session() -> requests.Session:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()

    # ── Proxy support ──────────────────────────────────────────
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    if https_proxy:
        session.proxies = {
            "http":  https_proxy,
            "https": https_proxy,
        }
        print(f"  🔀 Using proxy: {https_proxy}")
    else:
        print("  ⚠️  No HTTPS_PROXY set — connecting directly.")
    # ───────────────────────────────────────────────────────────

    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session

def _send_with_retry(session: requests.Session, text: str) -> dict | None:
    url = f"{TELEGRAM_API}/sendMessage"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.post(
                url,
                json={
                    "chat_id":    CHAT_ID,
                    "text":       text,
                    "parse_mode": "Markdown",
                },
                timeout=20,
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", BACKOFF_BASE * attempt))
                print(f"    ⏳ Rate limited. Waiting {retry_after}s (attempt {attempt})...")
                time.sleep(retry_after)
                continue

            resp.raise_for_status()
            data = resp.json()

            if data.get("ok"):
                return data
            else:
                print(f"    ⚠️  Telegram ok=false: {data.get('description')}")
                return None

        except (requests.ConnectionError, requests.Timeout, ConnectionResetError) as e:
            wait = BACKOFF_BASE * (2 ** (attempt - 1))
            print(f"    ⚠️  Connection error (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                print(f"    ↻  Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"    ❌ Giving up after {MAX_RETRIES} attempts.")
                return None

    return None


def _load_archive() -> list:
    if os.path.exists(ARCHIVE_PATH):
        with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_archive(archive: list) -> None:
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


def telegram_publish_node(state: dict) -> dict:
    print("\n📤 Publishing to Telegram...")

    posts: list[dict] = state.get("generated_posts", [])

    if not posts:
        generated_path = state.get("generated_path", "src/data/generated_news.json")
        if os.path.exists(generated_path):
            with open(generated_path, "r", encoding="utf-8") as f:
                posts = json.load(f)

    if not posts:
        print("⚠️  No generated posts found — skipping publish.")
        return {**state, "status": "publish_skipped", "published_count": 0}

    session          = _make_session()
    archive          = _load_archive()
    published_count  = 0
    failed_count     = 0
    published_at     = datetime.now().isoformat()

    for idx, post in enumerate(posts, 1):
        text = post.get("generated_post", "").strip()
        if not text:
            continue

        print(f"  → Sending post {idx}/{len(posts)}...")
        result = _send_with_retry(session, text)

        if result:
            message_id = result["result"]["message_id"]
            print(f"  ✅ Sent (message_id={message_id})")
            archive.append({
                "published_at":   published_at,
                "message_id":     message_id,
                "cluster_index":  post.get("cluster_index"),
                "article_count":  post.get("article_count"),
                "source_titles":  post.get("source_titles", []),
                "generated_post": text,
            })
            published_count += 1
        else:
            failed_count += 1

        if idx < len(posts):
            time.sleep(SEND_DELAY)

    _save_archive(archive)

    print(f"\n✅ Published: {published_count}  |  Failed: {failed_count}")
    print(f"💾 Archive saved → {ARCHIVE_PATH}  ({len(archive)} total entries)")

    return {
        **state,
        "status":          "published",
        "published_count": published_count,
        "failed_count":    failed_count,
        "archive_path":    ARCHIVE_PATH,
    }