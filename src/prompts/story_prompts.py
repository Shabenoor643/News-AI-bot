import re

from src.config.config import CONFIG


STORY_SYSTEM_PROMPT = f"""You are NewsBot's Senior Motorcycle Journalist, Buyer Advisor, and Market Analyst.

Process one motorcycle news cluster in a single API call.

Your job:
1. Extract the bike name, brand, category, story type, and major updates.
2. Cross-check all sources and keep only source-supported claims in the article.
3. Ignore conflicting or weak claims in the final article body.
4. Enrich the story with India-specific pricing context, rivals, and buyer advice.
5. Write one clean Markdown article that is ready to paste into a CMS or email.

Article rules:
- The first 2 lines are a hook with curiosity, the bike name, and why it matters.
- Use these exact H2 headings in this exact order:
  ## What's new
  ## Design / Features
  ## Engine / Performance
  ## Price & Positioning
  ## Should You Care?
- Article length: {CONFIG.Pipeline.article_min_words}-{CONFIG.Pipeline.article_max_words} words.
- Most sentences should stay between 10 and 18 words.
- Keep paragraphs short, usually 2 or 3 sentences.
- Tone: conversational, expert, specific, and human.
- Include value-for-money context, rival positioning, target buyer type, and beginner suitability.
- If pricing or specs are not fully confirmed, say so plainly.

Do not include:
- hashtags
- FAQ sections
- table of contents
- emojis
- "In conclusion"
- "In this article"
- markdown code fences
- metadata inside the article body

Validation rules:
- Facts in 2 or more sources are verified.
- Facts in only 1 source are unverified and stay out of the article body unless clearly labelled as tentative.
- Conflicting facts stay out of the article body.
- Never invent launch dates, prices, specifications, rivals, or dealer details.

Output must be valid JSON matching the provided schema."""

STORY_CLUSTER_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "story": {
            "type": "OBJECT",
            "properties": {
                "bike_name": {"type": "STRING"},
                "brand": {"type": "STRING"},
                "category": {"type": "STRING"},
                "story_type": {"type": "STRING"},
                "headline_summary": {"type": "STRING"},
                "highlights": {"type": "ARRAY", "items": {"type": "STRING"}},
                "competitors": {"type": "ARRAY", "items": {"type": "STRING"}},
                "expected_price_range": {"type": "STRING"},
                "buyer_relevance": {"type": "STRING"},
                "target_buyer": {"type": "STRING"},
                "beginner_fit": {"type": "STRING"},
                "validation": {
                    "type": "OBJECT",
                    "properties": {
                        "verified_facts": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "ignored_unverified_claims": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "ignored_conflicting_claims": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "confidence_score": {"type": "NUMBER"},
                    },
                    "required": [
                        "verified_facts",
                        "ignored_unverified_claims",
                        "ignored_conflicting_claims",
                        "confidence_score",
                    ],
                },
            },
            "required": [
                "bike_name",
                "brand",
                "category",
                "story_type",
                "headline_summary",
                "highlights",
                "competitors",
                "expected_price_range",
                "buyer_relevance",
                "target_buyer",
                "beginner_fit",
                "validation",
            ],
        },
        "article": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "meta_description": {"type": "STRING"},
                "slug": {"type": "STRING"},
                "keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
                "markdown": {"type": "STRING"},
            },
            "required": ["title", "meta_description", "slug", "keywords", "markdown"],
        },
    },
    "required": ["story", "article"],
}

ARTICLE_ONLY_SCHEMA = STORY_CLUSTER_SCHEMA["properties"]["article"]

FALLBACK_STORY_PROMPT = """There is no strong breaking motorcycle cluster right now.
Create one evergreen, finance-aware motorcycle article for Indian readers.
Keep it practical, buyer-focused, and structured with the required headings."""


def _normalize_snippet(text: str, max_chars: int = 360) -> str:
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    return compact[:max_chars]


def build_story_prompt(cluster: dict, items: list[dict]) -> str:
    lines = [
        f"Canonical topic: {cluster.get('canonical_topic') or 'Motorcycle update'}",
        f"Cluster story type hint: {cluster.get('story_type') or 'news'}",
        f"Cluster source count: {len(items)}",
        "Use only the source-backed details below.",
        "Source notes:",
    ]

    seen_rows = set()
    for index, item in enumerate(items[:6], start=1):
        title = _normalize_snippet(item.get("title"), 180)
        snippet = _normalize_snippet(item.get("snippet") or item.get("full_text"), 420)
        published_at = item.get("published_at") or "unknown"
        url = str(item.get("url") or "unknown").strip()
        dedupe_key = (title.lower(), snippet.lower(), url.lower())
        if dedupe_key in seen_rows:
            continue
        seen_rows.add(dedupe_key)

        lines.extend(
            [
                f"Source {index} title: {title}",
                f"Source {index} published_at: {published_at}",
                f"Source {index} url: {url}",
                f"Source {index} snippet: {snippet}",
            ]
        )

    return "\n".join(lines).strip()
