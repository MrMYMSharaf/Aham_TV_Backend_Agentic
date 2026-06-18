import json
import os

INPUT_PATH  = "src/data/generated_news.json"
OUTPUT_PATH = "src/data/output.txt"

FOOTER = (
    "\n━━━━━━━━━━━━━━━━━━━━\n"
    "📲 Follow our page for the latest updates!\n"
    "🌐 https://chat.whatsapp.com/E8VeTVibnBA5bxwa5wawyS?mode=hqctshi\n"
    "👍 Like & Share to spread the news!\n"
    "━━━━━━━━━━━━━━━━━━━━"
)

# Old footer the LLM already appended — strip this before adding ours
OLD_FOOTER = (
    "📲 Follow our page for the latest updates!\n"
    "👍 Like & Share to spread the news!\n"
    "━━━━━━━━━━━━━━━━━━━━"
)


def clean_text(text: str) -> str:
    """Remove the old LLM footer so we can add the updated one cleanly."""
    if OLD_FOOTER in text:
        text = text[:text.index(OLD_FOOTER)].rstrip("━").rstrip()
    return text


def print_posts():
    if not os.path.exists(INPUT_PATH):
        print(f"❌ File not found: {INPUT_PATH}")
        return

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        posts = json.load(f)

    print(f"✅ Found {len(posts)} posts\n")

    lines = []

    for post in posts:
        idx   = post.get("cluster_index", "?")
        count = post.get("article_count", 0)
        text  = clean_text(post.get("generated_post", "")) + FOOTER

        block = (
            f"\n📌 POST {idx}  |  {count} article(s)\n"
            f"{'-' * 60}\n"
            f"{text}\n"
            f"{'=' * 60}"
        )

        print(block)
        lines.append(block)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n💾 Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    print_posts()