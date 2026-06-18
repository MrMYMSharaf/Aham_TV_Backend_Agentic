import asyncio
import json
import re
import traceback
import feedparser
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


# ---------------------------
# GLOBAL NOISE PATTERNS
# ---------------------------
GLOBAL_NOISE = [
    "WATCH LIVE", "MORE..", "READ MORE", "Click here",
    "Subscribe", "Sign up", "Daily FT", "Sunday May",
    "All rights Reserved", "Developed by", "Designed by",
    "Privacy Policy", "Design & Development by",
    "Save my name, email", "Lakehouse IT",
    "©2026", "@2026", "next time I comment",
]


# ---------------------------
# CLEAN CONTENT
# ---------------------------
def clean_content(text: str, site_config: dict) -> str:
    if not text:
        return ""

    for phrase in GLOBAL_NOISE:
        text = text.replace(phrase, "")

    spam_pattern = site_config.get("spam_pattern")
    if spam_pattern and spam_pattern in text:
        text = text[:text.index(spam_pattern)]

    noise_suffix = site_config.get("noise_suffix")
    if noise_suffix and noise_suffix in text:
        text = text[:text.index(noise_suffix)]

    # Remove trailing junk after double dot
    text = re.sub(r'\.\.\s+[A-Za-z][\w\s\-]{0,30}$', '', text)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text[:2000]


# ---------------------------
# RSS FALLBACK FETCHER
# ---------------------------
def fetch_rss(site_config: dict) -> list:
    rss_url = site_config.get("rss_url")
    if not rss_url:
        return []

    print(f"   → Trying RSS: {rss_url}")
    try:
        # Use requests to fetch RSS (more reliable than feedparser direct)
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"
        }
        resp = requests.get(rss_url, headers=headers, timeout=10)
        resp.raise_for_status()

        feed = feedparser.parse(resp.content)

        if not feed.entries:
            print(f"   ⚠️ RSS returned 0 entries")
            return []

        results = []
        seen = set()

        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            content = ""

            if hasattr(entry, "content"):
                content = BeautifulSoup(
                    entry.content[0].value, "html.parser"
                ).get_text(" ", strip=True)
            elif hasattr(entry, "summary"):
                content = BeautifulSoup(
                    entry.summary, "html.parser"
                ).get_text(" ", strip=True)

            if not title or len(title) < 10 or link in seen:
                continue

            seen.add(link)
            results.append({
                "source": site_config["title"],
                "language": site_config.get("language", "English"),
                "title": title,
                "link": link,
                "content": clean_content(content, site_config)
            })

        print(f"   → RSS got {len(results)} articles")
        return results

    except Exception as e:
        print(f"   ⚠️ RSS error: {e}")
        return []
# ---------------------------
# REQUESTS-BASED FETCHER (for antibot sites)
# ---------------------------
def fetch_with_requests(site_config: dict) -> list:
    url = site_config["url"]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ta;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    print(f"   → Trying requests fallback for {url}")
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        news_data = []
        seen_links = set()
        seen_titles = set()

        selector = site_config.get("article_selector", "")
        elements = soup.select(selector) if selector else []

        if not elements:
            elements = soup.find_all("a", href=True)

        skip_keywords = [
            "category", "tag", "author", "about", "contact",
            "privacy", "advertise", "subscribe", "facebook",
            "twitter", "youtube", "instagram", "feed", "rss"
        ]

        for element in elements:
            try:
                a_tag = element if element.name == "a" else element.find("a", href=True)
                if not a_tag:
                    continue

                title = a_tag.get_text(strip=True)
                link = a_tag.get("href", "")

                if not title or len(title) < 20:
                    continue
                if not link or link.startswith("#"):
                    continue
                if any(kw in link.lower() for kw in skip_keywords):
                    continue
                if not re.search(r'/\d{4,}|/[a-z0-9-]{10,}', link):
                    continue

                link = urljoin(url, link)

                if link in seen_links or title in seen_titles:
                    continue
                seen_links.add(link)
                seen_titles.add(title)

                news_data.append({
                    "source": site_config["title"],
                    "language": site_config.get("language", "English"),
                    "title": title,
                    "link": link,
                    "content": ""
                })

            except Exception:
                continue

        print(f"   → requests fetched {len(news_data)} articles")
        return news_data[:10]

    except Exception as e:
        print(f"   ⚠️ Requests error: {e}")
        return []


def fetch_article_content_requests(link: str, site_config: dict) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(link, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        content_text = ""

        selector = site_config.get("content_selector", "")
        if selector:
            for sel in selector.split(","):
                block = soup.select_one(sel.strip())
                if block:
                    content_text = block.get_text(" ", strip=True)
                    if len(content_text) > 100:
                        break

        if not content_text or len(content_text) < 100:
            paragraphs = soup.find_all("p")
            content_text = " ".join(
                p.get_text(strip=True)
                for p in paragraphs
                if len(p.get_text(strip=True)) > 40
            )

        return clean_content(content_text, site_config)
    except Exception:
        return ""


# ---------------------------
# SCRAPE HEADLINES (crawl4ai)
# ---------------------------
async def scrape_site(crawler, site_config, run_cfg):
    url = site_config["url"]
    print(f"\n🔄 Scraping {site_config['title']} -> {url}")

    try:
        result = await crawler.arun(url=url, config=run_cfg)
    except Exception as e:
        print(f"   ⚠️ crawl4ai error: {e}")
        return []

    if not result or not result.success:
        print(f"   ❌ Failed to fetch {url}")
        return []

    html = result.cleaned_html
    soup = BeautifulSoup(html, "html.parser")

    news_data = []
    seen_links = set()
    seen_titles = set()

    articles = soup.select(site_config.get("article_selector", ""))

    if not articles:
        print("   ⚠️ Selector failed, using fallback <a> extraction")
        articles = soup.find_all("a", href=True)

    skip_keywords = [
        "category", "tag", "author", "page", "Weekend_Online",
        "about", "contact", "privacy", "advertise", "subscribe",
        "youtube.com", "facebook.com", "twitter.com", "instagram.com",
        "pressreader", "epaper", "search", "login", "register",
        "/feed", "rss", "mailto:"
    ]

    for element in articles:
        try:
            a_tag = element if element.name == "a" else element.find("a", href=True)
            if not a_tag:
                continue

            title = a_tag.get_text(strip=True)
            link = a_tag.get("href", "")

            if not title or len(title) < 20:
                continue
            if not link or link.startswith("#") or link.startswith("javascript"):
                continue
            if any(kw.lower() in link.lower() for kw in skip_keywords):
                continue
            if not re.search(r'/\d{4,}|/[a-z0-9-]{10,}', link):
                continue

            link = urljoin(url, link)

            if link in seen_links or title in seen_titles:
                continue
            seen_links.add(link)
            seen_titles.add(title)

            news_data.append({
                "source": site_config["title"],
                "language": site_config.get("language", "English"),
                "title": title,
                "link": link,
                "content": ""
            })

        except Exception:
            continue

    print(f"   → {len(news_data)} unique articles found")
    return news_data


# ---------------------------
# FETCH ARTICLE CONTENT (crawl4ai)
# ---------------------------
async def fetch_content(crawler, item, site_config, run_cfg):
    try:
        if not item.get("link"):
            return item

        fetch_delay = site_config.get("fetch_delay", 0)
        if fetch_delay:
            await asyncio.sleep(fetch_delay)

        result = await crawler.arun(url=item["link"], config=run_cfg)

        if not result or not result.success:
            item["content"] = ""
            return item

        soup = BeautifulSoup(result.cleaned_html, "html.parser")
        content_text = ""
        content_selector = site_config.get("content_selector", "")

        if content_selector:
            for selector in content_selector.split(","):
                block = soup.select_one(selector.strip())
                if block:
                    content_text = block.get_text(" ", strip=True)
                    if len(content_text) > 100:
                        break

        if not content_text or len(content_text) < 100:
            paragraphs = soup.find_all("p")
            content_text = " ".join(
                p.get_text(strip=True)
                for p in paragraphs
                if len(p.get_text(strip=True)) > 40
            )

        item["content"] = clean_content(content_text, site_config)

    except Exception as e:
        print(f"   ⚠️ Content error: {item.get('link')} -> {e}")
        item["content"] = ""

    return item


# ---------------------------
# BUILD CRAWLER CONFIG
# ---------------------------
def get_run_config(js_required: bool) -> CrawlerRunConfig:
    if js_required:
        return CrawlerRunConfig(
            wait_until="networkidle",
            page_timeout=60000,  # 60 seconds
            delay_before_return_html=5.0,
            js_code="window.scrollTo(0, document.body.scrollHeight);"
        )
    return CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=60000  # 60 seconds
    )


# ---------------------------
# PROCESS ONE SITE
# ---------------------------
async def process_site(crawler, site):
    site_title = site["title"]
    js_required = site.get("js_required", False)
    use_requests = site.get("use_requests", False)
    rss_url = site.get("rss_url")
    run_cfg = get_run_config(js_required)

    # ── Strategy 1: RSS (highest priority, antibot bypass) ──
    if rss_url:
        headlines = fetch_rss(site)
        if headlines:
            print(f"   ✅ RSS success: {len(headlines)} articles")
            return headlines
        else:
            print(f"   ⚠️ RSS empty, skipping {site_title}")
            return []   # Don't fall through to crawl4ai for antibot sites

    # ── Strategy 2: requests (for antibot or JS-heavy sites) ──
    if use_requests:
        headlines = fetch_with_requests(site)
        if headlines:
            for item in headlines:
                item["content"] = fetch_article_content_requests(item["link"], site)
                await asyncio.sleep(0.3)
            print(f"   ✅ requests success: {len(headlines)} articles")
            return headlines
        else:
            print(f"   ⚠️ requests failed for {site_title}")
            return []

    # ── Strategy 3: crawl4ai (default) ──
    headlines = await scrape_site(crawler, site, run_cfg)

    if not headlines:
        print(f"   ⚠️ No articles found for {site_title}")
        return []

    headlines = headlines[:10]
    fetched = []
    for item in headlines:
        item = await fetch_content(crawler, item, site, run_cfg)
        fetched.append(item)
        await asyncio.sleep(0.5)

    return fetched
# ---------------------------
# MAIN PIPELINE
# ---------------------------
async def main():
    try:
        with open("src/url/url.json", "r", encoding="utf-8") as f:
            sites = json.load(f)

        all_news = []
        stats = {}

        browser_cfg = BrowserConfig(
            headless=True,
            java_script_enabled=True,
            viewport_width=1280,
            viewport_height=800
        )

        async with AsyncWebCrawler(config=browser_cfg, verbose=False) as crawler:
            for site in sites:
                site_title = site["title"]
                try:
                    fetched = await process_site(crawler, site)
                    all_news.extend(fetched)
                    stats[site_title] = {
                        "articles": len(fetched),
                        "with_content": sum(
                            1 for a in fetched if len(a.get("content", "")) > 100
                        )
                    }
                except Exception as e:
                    print(f"🔥 Site error [{site_title}]: {e}")
                    traceback.print_exc()
                    stats[site_title] = {"articles": 0, "with_content": 0}

        # Save output
        output_path = "src/data/all_news_data.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_news, f, ensure_ascii=False, indent=2)

        # Print report
        print("\n" + "=" * 55)
        print("📊  SCRAPING REPORT")
        print("=" * 55)
        total_articles = 0
        total_with_content = 0
        for site_name, s in stats.items():
            filled = s["with_content"]
            total = s["articles"]
            total_articles += total
            total_with_content += filled
            pct = int((filled / total * 100) if total > 0 else 0)
            bar = "█" * filled + "░" * max(0, total - filled)
            status = "✅" if pct >= 70 else "⚠️" if pct >= 30 else "❌"
            print(f"  {status} {site_name:<22} | {bar:<10} {filled}/{total} ({pct}%)")

        print("=" * 55)
        overall = int(total_with_content / total_articles * 100) if total_articles else 0
        print(f"  Overall: {total_with_content}/{total_articles} ({overall}%)")
        print(f"\n🎉 DONE! Total articles saved: {len(all_news)}")
        print(f"📁 Output: {output_path}")

    except Exception as e:
        print("🔥 CRITICAL ERROR")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())