import os
import json
import boto3
from datetime import datetime
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
MODEL_ID = (
    "arn:aws:bedrock:us-east-1:775412354642:"
    "inference-profile/us.meta.llama3-3-70b-instruct-v1:0"
)
OUTPUT_PATH = "src/data/generated_news.json"
MAX_ARTICLES_PER_CLUSTER = 3   # Feed top-N articles per cluster to the LLM


def _build_client():
    return boto3.client(
        service_name="bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("AWS_SECRET_KEY"),
    )


def _build_raw_input(cluster: list[dict]) -> str:
    """
    Flatten the top articles in a cluster into a single readable block
    the LLM can digest as raw news input.
    """
    snippets = []
    for i, article in enumerate(cluster[:MAX_ARTICLES_PER_CLUSTER], 1):
        title   = article.get("title", "").strip()
        content = article.get("content", article.get("summary", "")).strip()
        source  = article.get("source", "Unknown source")
        lang    = article.get("language", "")
        snippets.append(
            f"[Article {i} | {source}{' | ' + lang if lang else ''}]\n"
            f"Title: {title}\n"
            f"{content[:600]}"          # cap to avoid blowing the context window
        )
    return "\n\n---\n\n".join(snippets)


def _generate_post(client, raw_news: str, today: str) -> str:
    """Call Bedrock and return the generated WhatsApp news post."""

    system_prompt = (
        "You are a senior multilingual journalist and WhatsApp news channel editor. "
        "You specialize in writing breaking news for Sri Lankan audiences in three languages: "
        "English, Sinhala (සිංහල), and Tamil (தமிழ்).\n\n"
        "Your writing style is:\n"
        "- Clear, factual, and trustworthy\n"
        "- Engaging and easy to read on mobile\n"
        "- Culturally appropriate for each language audience\n"
        "- Formatted perfectly for WhatsApp (uses emojis sparingly but effectively)\n\n"
        "You never fabricate facts. You only work with the information provided."
    )

    user_prompt = f"""You will receive one or more raw news pieces below. \
Read them all, extract the key facts, and produce a single unified, \
professional WhatsApp news post in all three languages.

---
RAW NEWS INPUT:
{raw_news}
---

OUTPUT FORMAT (follow exactly — no deviations):

🗞️ *NEWS FLASH* 🗞️
━━━━━━━━━━━━━━━━━━━━

🇬🇧 *ENGLISH*
📅 Date: {today}
📌 *[Compelling, hook-style headline — max 12 words]*

[3–4 clear, factual sentences in English.]

━━━━━━━━━━━━━━━━━━━━

🇱🇰 *SINHALA | සිංහල*
📅 දිනය: {today}
📌 *[Same headline in natural Sinhala]*

[3–4 sentences in fluent Sinhala.]

━━━━━━━━━━━━━━━━━━━━

🇮🇳 *TAMIL | தமிழ்*
📅 தேதி: {today}
📌 *[Same headline in natural Tamil]*

[3–4 sentences in fluent Tamil.]

━━━━━━━━━━━━━━━━━━━━
📲 Follow our page for the latest updates!
👍 Like & Share to spread the news!
━━━━━━━━━━━━━━━━━━━━

STRICT RULES:
- All three language sections are MANDATORY — never skip one
- Headlines must be under 12 words and feel urgent
- Never add facts not present in the raw input
- Use the exact separator (━) format shown above
- Total output must stay under 600 tokens"""

    response = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        system=[{"text": system_prompt}],
        inferenceConfig={
            "temperature": 0.5,
            "maxTokens": 2000,
            "topP": 0.9,
        },
    )
    return response["output"]["message"]["content"][0]["text"]


# ─────────────────────────────────────────
# LANGGRAPH NODE
# ─────────────────────────────────────────
def content_generation_node(state: dict) -> dict:
    print("\n✍️  Generating multilingual news posts...")

    clusters_path = state.get("clusters_path", "src/data/clusters.json")
    with open(clusters_path, "r", encoding="utf-8") as f:
        clusters: list[list[dict]] = json.load(f)

    client = _build_client()
    today  = datetime.now().strftime("%d/%m/%Y")

    generated_posts = []
    errors          = []

    for idx, cluster in enumerate(clusters, 1):
        if not cluster:
            continue

        print(f"  → Cluster {idx}/{len(clusters)} "
              f"({len(cluster)} article{'s' if len(cluster) > 1 else ''})...")

        raw_news = _build_raw_input(cluster)

        try:
            post_text = _generate_post(client, raw_news, today)
            generated_posts.append({
                "cluster_index":   idx,
                "article_count":   len(cluster),
                "source_titles":   [a.get("title", "") for a in cluster[:MAX_ARTICLES_PER_CLUSTER]],
                "generated_post":  post_text,
            })
        except ClientError as e:
            msg = f"Cluster {idx} — AWS error: {e}"
            print(f"  ⚠️  {msg}")
            errors.append(msg)
        except Exception as e:
            msg = f"Cluster {idx} — Error: {e}"
            print(f"  ⚠️  {msg}")
            errors.append(msg)

    # Persist to disk
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(generated_posts, f, ensure_ascii=False, indent=2)

    print(f"✅  Generated {len(generated_posts)} posts → {OUTPUT_PATH}")
    if errors:
        print(f"⚠️  {len(errors)} cluster(s) failed: {errors}")

    return {
        **state,
        "status":          "generated",
        "posts_count":     len(generated_posts),
        "generated_posts": generated_posts,
        "generated_path":  OUTPUT_PATH,
    }