import asyncio
import json
from typing import TypedDict
from langgraph.graph import END, StateGraph, START

from scrapper.web_scraper         import main as run_scraper
from embedding.embedder           import embed_articles
from similarity.clustering        import cluster_articles
from contentCreatorAgent.news_generator  import content_generation_node
from telegram_bot.messagesend import telegram_publish_node


# ─────────────────────────────────────────
# STATE
# ─────────────────────────────────────────
class State(TypedDict):
    # Pipeline lifecycle
    status:          str
    error:           str

    # Scrape
    output_path:     str

    # Embed
    articles_saved:  int
    embedded_path:   str
    embedded_articles: list

    # Cluster
    clusters_count:  int
    clusters_path:   str

    # Generate
    posts_count:     int
    generated_posts: list
    generated_path:  str

    # Publish
    published_count: int
    failed_count:    int
    archive_path:    str


# ─────────────────────────────────────────
# NODE 1: Scrape
# ─────────────────────────────────────────
def run_scraper_node(state: State) -> State:
    print("🚀 LangGraph: Starting scraper node...")
    try:
        asyncio.run(run_scraper())
        return {
            **state,
            "status":      "scraped",
            "output_path": "src/data/all_news_data.json",
            "error":       "",
        }
    except Exception as e:
        return {**state, "status": "failed", "error": str(e)}


# ─────────────────────────────────────────
# NODE 2: Embed
# ─────────────────────────────────────────
def embedding_node(state: State) -> State:
    print("\n🧠 Embedding articles...")

    output_path = state.get("output_path", "")
    with open(output_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    embedded_articles    = embed_articles(articles)
    output_embed_path    = "src/data/embedded_news.json"

    with open(output_embed_path, "w", encoding="utf-8") as f:
        json.dump(embedded_articles, f, ensure_ascii=False, indent=2)

    print(f"💾 Saved embeddings → {output_embed_path}")
    print(f"✅ Embedded {len(embedded_articles)} articles")

    return {
        **state,
        "status":            "embedded",
        "articles_saved":    len(embedded_articles),
        "output_path":       output_path,
        "embedded_path":     output_embed_path,
        "embedded_articles": embedded_articles,
    }


# ─────────────────────────────────────────
# NODE 3: Cluster
# ─────────────────────────────────────────
def clustering_node(state: State) -> State:
    print("\n🔗 Clustering similar news...")

    articles = state.get("embedded_articles", [])
    if not articles:
        raise ValueError("No embedded articles found in state")

    clusters             = cluster_articles(articles, threshold=0.85)
    output_cluster_path  = "src/data/clusters.json"

    with open(output_cluster_path, "w", encoding="utf-8") as f:
        json.dump(clusters, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(clusters)} clusters → {output_cluster_path}")

    return {
        **state,
        "status":        "clustered",
        "clusters_count": len(clusters),
        "clusters_path": output_cluster_path,
    }


# ─────────────────────────────────────────
# ROUTERS
# ─────────────────────────────────────────
def route_after_scrape(state: State) -> str:
    if state["status"] == "failed":
        print(f"❌ Scraper failed: {state['error']}")
        return END
    return "embedding"


def route_after_generate(state: State) -> str:
    """Skip publishing if nothing was generated."""
    if state.get("posts_count", 0) == 0:
        print("⚠️  No posts generated — skipping Telegram publish.")
        return END
    return "publish"


# ─────────────────────────────────────────
# BUILD GRAPH
# ─────────────────────────────────────────
workflow_builder = StateGraph(State)

workflow_builder.add_node("scrape",    run_scraper_node)
workflow_builder.add_node("embedding", embedding_node)
workflow_builder.add_node("clustering", clustering_node)
workflow_builder.add_node("generate",  content_generation_node)
workflow_builder.add_node("publish",   telegram_publish_node)

workflow_builder.add_edge(START, "scrape")
workflow_builder.add_conditional_edges("scrape",    route_after_scrape)
workflow_builder.add_edge("embedding",  "clustering")
workflow_builder.add_edge("clustering", "generate")
workflow_builder.add_conditional_edges("generate",  route_after_generate)
workflow_builder.add_edge("publish",    END)

workflow = workflow_builder.compile()


# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────
if __name__ == "__main__":
    initial_state: State = {
        "status":            "pending",
        "error":             "",
        "output_path":       "",
        "articles_saved":    0,
        "embedded_path":     "",
        "embedded_articles": [],
        "clusters_count":    0,
        "clusters_path":     "",
        "posts_count":       0,
        "generated_posts":   [],
        "generated_path":    "",
        "published_count":   0,
        "failed_count":      0,
        "archive_path":      "",
    }

    final_state = workflow.invoke(initial_state)

    print("\n📦 FINAL RESULT")
    print("=" * 40)
    print(f"Status           : {final_state['status']}")
    print(f"Articles embedded: {final_state.get('articles_saved', 0)}")
    print(f"Clusters formed  : {final_state.get('clusters_count', 0)}")
    print(f"Posts generated  : {final_state.get('posts_count', 0)}")
    print(f"Posts published  : {final_state.get('published_count', 0)}")
    print(f"Publish failures : {final_state.get('failed_count', 0)}")
    print(f"Archive path     : {final_state.get('archive_path', '—')}")