from src.utils.llm_service import LLMService
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

from src.config.config import CONFIG
from src.db.queries.story_clusters import insert_extracted_story
from src.db.queries.draft_articles import insert_draft_article, slug_exists
from src.utils.error_handler import GeminiInputError, handle_error
from src.utils.logger import create_logger
from src.utils.parse_gemini_json import parse_gemini_json
from src.utils.sleep import sleep

logger = create_logger("story_agent")
ALLOWED_CATEGORIES = {"launch", "review", "news", "racing", "ev", "recall", "comparison", "price_drop", "price_hike", "discontinued", "top_list", "evergreen", "update"}

ARTICLE_PROMPT_TEMPLATE = """Act as an expert automotive content writer and SEO strategist.

Generate a high-quality, SEO-optimized blog article.

REQUIREMENTS:

- Output must include:
    • SEO Title (max 60 chars)
    • Meta Description (140-155 chars)
    • URL Slug (SEO-friendly, lowercase, hyphenated)

- Writing Style:
    • Conversational, human-like, engaging
    • No fluff, no robotic tone

- Structure:
    • Strong hook-based introduction
    • Use H2 and H3 headings
    • Short paragraphs (2-3 lines max)
    • No Table of Contents
    • No FAQs

- SEO:
    • Use primary keyword naturally
    • Include secondary keywords organically
    • Optimize for featured snippets

- Content Depth:
    • Add latest insights (current year context)
    • Add competitor comparisons
    • Include real-world usage (city/highway)
    • Define target audience

- Formatting:
    • Bullet points only for specs/features

- Avoid:
    • Repetition
    • Generic filler lines

Template variables:
- {{topic}}
- {{primary_keyword}}
- {{secondary_keywords}}

OUTPUT FORMAT (STRICT):
SEO Title:
Meta Description:
URL Slug:
Article:
"""

COMBINED_SYSTEM_PROMPT = f"""You are a senior automotive journalist and fact-checker for NewsBot (India).

Your task is to process a cluster of news sources and perform 3 tasks simultaneously:

1. EXTRACT: Summarize the story, extract key facts, entities, and quotes.

2. VALIDATE: For each extracted fact, mark as "verified" (in 2+ sources), "unverified" (1 source), or "conflict".

3. DRAFT: Write 2-3 high-quality SEO-focused blog articles based on the story type.

Use this exact writing directive for each article:

{ARTICLE_PROMPT_TEMPLATE}

OUTPUT FORMAT (STRICT):
SEO Title:
Meta Description:
URL Slug:
Article:

Map the strict format to schema fields as follows:
- SEO Title -> title
- Meta Description -> meta_description
- URL Slug -> slug
- Article -> article

---

Return the result STRICTLY matching the requested JSON schema.
"""

COMBINED_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "story": {
            "type": "OBJECT",
            "properties": {
                "headline_summary": {"type": "STRING"},
                "key_facts": {"type": "ARRAY", "items": {"type": "STRING"}},
                "entities": {
                    "type": "OBJECT",
                    "properties": {
                        "bike_models": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "brands": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "people": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "locations": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "dates": {"type": "ARRAY", "items": {"type": "STRING"}}
                    },
                    "required": ["bike_models", "brands", "people", "locations", "dates"]
                },
                "event_type": {"type": "STRING"},
                "quoted_statements": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "speaker": {"type": "STRING"},
                            "quote": {"type": "STRING"}
                        },
                        "required": ["speaker", "quote"]
                    }
                },
                "single_source_fields": {"type": "ARRAY", "items": {"type": "STRING"}},
                "facts_validation": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "fact": {"type": "STRING"},
                            "status": {"type": "STRING", "enum": ["verified", "unverified", "conflict"]},
                            "conflict_values": {"type": "ARRAY", "items": {"type": "STRING"}}
                        },
                        "required": ["fact", "status"]
                    }
                }
            },
            "required": ["headline_summary", "key_facts", "entities", "event_type", "quoted_statements", "single_source_fields", "facts_validation"]
        },
        "articles": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "type": {"type": "STRING"},
                    "title": {"type": "STRING"},
                    "meta_title": {"type": "STRING"},
                    "meta_description": {"type": "STRING"},
                    "keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "slug": {"type": "STRING"},
                    "article": {"type": "STRING"}
                },
                "required": ["type", "title", "meta_title", "meta_description", "keywords", "slug", "article"]
            }
        }
    },
    "required": ["story", "articles"]
}

def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower())
    slug = re.sub(r"(^-+|-+$)", "", slug)
    return slug[:80] or "untitled"


def ensure_unique_slug(base_slug: str) -> str:
    if not slug_exists(base_slug):
        return base_slug
    idx = 2
    while slug_exists(f"{base_slug}-{idx}"):
        idx += 1
    return f"{base_slug}-{idx}"

def build_combined_prompt(cluster: dict) -> str:
    items = cluster.get("items", [])
    seen_snippets = set()
    primary_keyword = cluster.get("canonical_topic") or "india two-wheeler news"
    secondary_keywords = "india bike launch, scooter price, motorcycle specs, city mileage, highway performance"
    lines = [
        f"Canonical topic: {cluster.get('canonical_topic')}",
        f"Template variables: {{topic}}={cluster.get('canonical_topic')}, {{primary_keyword}}={primary_keyword}, {{secondary_keywords}}={secondary_keywords}",
        "Sources:"
    ]
    for i, item in enumerate(items):
        snippet = item.get('snippet') or ''
        if snippet in seen_snippets:
            continue
        seen_snippets.add(snippet)
        snippet = snippet[:500]
        lines.extend([
            f"Source {i + 1}: {item.get('title')} (Published: {item.get('published_at') or 'unknown'})",
            f"Snippet: {snippet}",
        ])
    return "\n".join(lines)

FALLBACK_PROMPT = """
No specific news was found. Generate 3 evergreen SEO-optimized articles for the Indian motorcycle market.

Each article MUST follow the strict output format:
SEO Title:
Meta Description:
URL Slug:
Article:

No table of contents. No FAQ section.

Topics:
1. Top 10 Motorcycles in India This Month (₹ pricing, specs, comparison)
2. Best Mileage Bikes in India 2024 (detailed analysis, real-world data)
3. Best Motorcycles Under ₹2 Lakh in India (segment-wise breakdown)

Output must match the schema. For 'story' field, provide minimal valid data.
"""

async def call_combined_model(llm: LLMService, prompt: str, context_label: str = "story_agent"):
    config = types.GenerateContentConfig(
        system_instruction=COMBINED_SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=COMBINED_SCHEMA,
        temperature=0.3,
        max_output_tokens=16000,  # Increased for 1200-2000 word articles
    )
    try:
        return await llm.generate_content(
            model=CONFIG.Gemini.model,
            contents=prompt,
            config=config,
            context_label=context_label,
            parse_json=True
        )
    except Exception as error:
        status = getattr(error, "code", 0)
        if status == 400:
            logger.warning("Simplifying prompt due to 400 error")
            prompt += "\nReturn ONLY valid JSON strictly matching the schema."
            return await llm.generate_content(
                model=CONFIG.Gemini.model,
                contents=prompt,
                config=config,
                context_label=context_label,
                parse_json=True
            )
        raise error

def save_extracted_story(parsed_story: dict, cluster: dict) -> dict:
    story_id = str(uuid.uuid4())
    validations = parsed_story.get("facts_validation", [])
    verified_count = sum(1 for item in validations if item.get("status") == "verified")
    key_facts_len = len(parsed_story.get("key_facts", []))
    validation_score = (verified_count / key_facts_len) if key_facts_len else 0.0
    source_count = int(cluster.get("source_count", 0))
    hold_for_review = validation_score < CONFIG.Pipeline.validation_score_threshold and source_count < CONFIG.Pipeline.min_sources_for_validation
    
    field_confidences = {}
    for item in validations:
        field_confidences[item.get("fact")] = {
            "status": item.get("status"),
            "conflict_values": item.get("conflict_values", []),
        }
    
    story = {
        "story_id": story_id,
        "cluster_id": cluster.get("cluster_id"),
        "headline_summary": parsed_story.get("headline_summary"),
        "key_facts": parsed_story.get("key_facts", []),
        "entities": parsed_story.get("entities", {}),
        "event_type": parsed_story.get("event_type"),
        "quoted_statements": parsed_story.get("quoted_statements", []),
        "field_confidences": field_confidences,
        "validation_score": validation_score,
        "hold_for_review": hold_for_review,
        "source_count": source_count,
        "source_urls": [item.get("url") for item in cluster.get("items", [])],
        "source_snippets": [{
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "url": item.get("url"),
        } for item in cluster.get("items", [])],
    }
    insert_extracted_story(story)
    return story

from src.agents.critic_agent import evaluate_draft
from src.utils.llm_service import LLMService
import traceback

async def regenerate_generated_article(llm: LLMService, draft: dict, feedback: str) -> dict:
    prompt = f"""
    You previously drafted this article:
    Title: {draft.get('title')}
    Body: {draft.get('article')}
    
    The editor rejected it with the following feedback:
    {feedback}
    
    Please REWRITE the article addressing the feedback. Return strictly valid JSON matching the schema.
    """
    schema = COMBINED_SCHEMA["properties"]["articles"]["items"]
    
    try:
        response = await llm.generate_content(
            model=CONFIG.Gemini.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a senior automotive journalist. Follow editor feedback.",
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.4,
            ),
            context_label="regenerate_article",
            parse_json=True
        )
        
        draft["title"] = str(response.get("title", draft.get("title"))).strip()
        draft["meta_description"] = str(response.get("meta_description", draft.get("meta_description"))).strip()
        draft["slug"] = normalize_slug(response.get("slug") or response.get("title") or draft.get("title"))
        draft["article"] = str(response.get("article", draft.get("article"))).strip()
        draft["keywords"] = response.get("keywords", draft.get("keywords"))
        draft["type"] = response.get("type", draft.get("type"))
        return draft
    except Exception as error:
        logger.warning(f"Failed to regenerate article: {error}")
        return draft

async def process_and_save_drafts(parsed_articles: list, story_id: str, run_id: str, source_urls: list[str], llm: LLMService) -> list[dict]:
    saved_articles = []
    for draft in parsed_articles:
        # CRITIC LOOP
        max_retries = 2
        for attempt in range(max_retries + 1):
            eval_result = await evaluate_draft(llm, {"title": draft.get("title"), "meta_description": draft.get("meta_description"), "body": draft.get("article")})
            if eval_result.get("approved"):
                logger.info(f"Article '{draft.get('title')}' approved by critic.")
                break
            else:
                if attempt < max_retries:
                    logger.info(f"Article '{draft.get('title')}' rejected by critic. Regenerating (Attempt {attempt + 1}). Feedback: {eval_result.get('feedback')}")
                    draft = await regenerate_generated_article(llm, draft, eval_result.get("feedback"))
                else:
                    logger.warning(f"Article '{draft.get('title')}' rejected by critic after {max_retries} retries. Proceeding anyway.")

        article_type = draft.get("type", "news")
        if article_type not in ALLOWED_CATEGORIES:
            article_type = "news"
        
        tags = draft.get("keywords", [])[:6]
        approval_expires_at = (datetime.now(timezone.utc) + timedelta(hours=CONFIG.Pipeline.approval_timeout_hours)).isoformat()
        
        article = {
            "article_id": str(uuid.uuid4()),
            "story_id": story_id or "fallback_story",
            "parent_story_id": story_id,
            "run_id": run_id,
            "title": str(draft.get("title", "")).strip(),
            "meta_description": str(draft.get("meta_description", "")).strip(),
            "slug": ensure_unique_slug(normalize_slug(draft.get("slug") or draft.get("title"))),
            "body": str(draft.get("article", "")).strip(),
            "tags": tags,
            "category": article_type,
            "article_type": article_type,
            "seo_score": 0.0,
            "image_prompt": "Professional studio photograph of a modern motorcycle, photorealistic, 4k",
            "image_url": None,
            "image_source": None,
            "alt_text": None,
            "image_status": "pending",
            "source_urls": source_urls,
            "approval_status": "pending",
            "approved_by": None,
            "approved_at": None,
            "rejected_by": None,
            "rejected_reason": None,
            "edit_count": 0,
            "approval_expires_at": approval_expires_at,
            "scheduled_publish_at": None,
            "published_url": None,
            "pipeline_stage": "draft",
        }
        insert_draft_article(article)
        saved_articles.append(article)
        logger.info("Draft article generated", extra={"story_id": story_id, "article_id": article["article_id"], "slug": article["slug"]})
    return saved_articles

async def run_story_agent(clusters: list[dict], run_id: str) -> dict:
    try:
        llm = LLMService()
        all_saved_stories = []
        all_saved_drafts = []

        for cluster in clusters:
            await sleep(CONFIG.Gemini.rate_limit_delay_ms)
            prompt = build_combined_prompt(cluster)
            parsed = await call_combined_model(llm, prompt, "story_agent")
            
            # Save the extracted and validated story
            story_dict = save_extracted_story(parsed.get("story", {}), cluster)
            all_saved_stories.append(story_dict)

            # Save the content drafts if not held for review
            if not story_dict.get("hold_for_review"):
                drafts = await process_and_save_drafts(
                    parsed.get("articles", []),
                    story_dict["story_id"],
                    run_id,
                    story_dict["source_urls"],
                    llm,
                )
                all_saved_drafts.extend(drafts)
            else:
                logger.warning("Story held for review, not generating drafts", extra={"cluster_id": cluster.get("cluster_id")})

        logger.info("Story agent complete", extra={"clusters": len(clusters), "stories": len(all_saved_stories), "drafts": len(all_saved_drafts)})
        return {"stories": all_saved_stories, "drafts": all_saved_drafts}
    except Exception as error:
        raise handle_error(error, logger, {"agent": "story_agent", "run_id": run_id})

async def run_fallback_story_agent(run_id: str) -> list[dict]:
    try:
        llm = LLMService()
        await sleep(CONFIG.Gemini.rate_limit_delay_ms)
        parsed = await call_combined_model(llm, FALLBACK_PROMPT, "story_agent_fallback")
        
        # Save only drafts
        return await process_and_save_drafts(parsed.get("articles", []), None, run_id, [], llm)
    except Exception as error:
        raise handle_error(error, logger, {"agent": "story_agent_fallback", "run_id": run_id})

async def regenerate_article(llm: LLMService, draft: dict, feedback: str) -> dict:
    prompt = f"""
    You previously drafted this article:
    Title: {draft.get('title')}
    Body: {draft.get('body')}
    
    The editor rejected it with the following feedback:
    {feedback}
    
    Please REWRITE the article addressing the feedback. Return strictly valid JSON.
    """
    schema = COMBINED_SCHEMA["properties"]["articles"]["items"]
    
    try:
        response = await llm.generate_content(
            model=CONFIG.Gemini.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a senior automotive journalist. Follow editor feedback.",
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.4,
            ),
            context_label="regenerate_article",
            parse_json=True
        )
        
        draft["title"] = str(response.get("title", draft.get("title"))).strip()
        draft["meta_description"] = str(response.get("meta_description", draft.get("meta_description"))).strip()
        draft["slug"] = normalize_slug(response.get("slug") or response.get("title") or draft.get("title"))
        draft["body"] = str(response.get("article", draft.get("body"))).strip()
        draft["tags"] = response.get("keywords", draft.get("tags"))[:6]
        draft["edit_count"] = draft.get("edit_count", 0) + 1
        return draft
    except Exception as error:
        logger.warning(f"Failed to regenerate article {draft.get('article_id')}: {error}")
        return draft


# Active single-pass runtime path.
from src.db.queries.raw_items import get_raw_items_by_ids
from src.prompts.image_prompts import build_image_search_queries
from src.prompts.story_prompts import (
    ARTICLE_ONLY_SCHEMA,
    FALLBACK_STORY_PROMPT,
    STORY_CLUSTER_SCHEMA,
    STORY_SYSTEM_PROMPT,
    build_story_prompt,
)
from src.utils.article_quality import assess_article_quality
from src.utils.fingerprint import generate_fingerprint
from src.utils.observability import AgentTrace


def _normalize_meta_description_v3(text: str) -> str:
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if len(compact) <= 155:
        return compact
    return compact[:152].rstrip() + "..."


def _hydrate_cluster_items_v3(cluster: dict) -> list[dict]:
    if cluster.get("items"):
        return list(cluster.get("items") or [])
    item_ids = list(cluster.get("item_ids") or [])
    if not item_ids:
        return []
    return get_raw_items_by_ids(item_ids)


def _build_cluster_signature_v3(cluster: dict, items: list[dict]) -> str:
    canonical_topic = str(cluster.get("canonical_topic") or "").strip()
    tokens = sorted(generate_fingerprint(canonical_topic))
    for item in items[:6]:
        source_key = normalize_slug(item.get("url") or item.get("title") or "")
        if source_key:
            tokens.append(source_key)
    return "|".join(dict.fromkeys(filter(None, tokens)))


def _map_entities_v3(parsed_story: dict) -> dict:
    bike_name = str(parsed_story.get("bike_name") or "").strip()
    brand = str(parsed_story.get("brand") or "").strip()
    return {
        "bike_models": [bike_name] if bike_name else [],
        "brands": [brand] if brand else [],
        "people": [],
        "locations": ["India"],
        "dates": [],
    }


def _save_extracted_story_v3(parsed_story: dict, cluster: dict, source_urls: list[str]) -> dict:
    validation = parsed_story.get("validation") or {}
    verified_facts = [str(value).strip() for value in list(validation.get("verified_facts") or []) if str(value).strip()]
    ignored_unverified = [str(value).strip() for value in list(validation.get("ignored_unverified_claims") or []) if str(value).strip()]
    ignored_conflicts = [str(value).strip() for value in list(validation.get("ignored_conflicting_claims") or []) if str(value).strip()]

    field_confidences = {}
    for fact in verified_facts:
        field_confidences[fact] = {"status": "verified", "conflict_values": []}
    for fact in ignored_unverified:
        field_confidences[fact] = {"status": "unverified", "conflict_values": []}
    for fact in ignored_conflicts:
        field_confidences[fact] = {"status": "conflict", "conflict_values": []}

    confidence_score = float(validation.get("confidence_score") or 0.0)
    if confidence_score > 1:
        confidence_score /= 100.0
    confidence_score = max(0.0, min(confidence_score, 1.0))

    story = {
        "story_id": str(uuid.uuid4()),
        "cluster_id": cluster.get("cluster_id"),
        "headline_summary": str(parsed_story.get("headline_summary") or "").strip(),
        "key_facts": verified_facts[:12],
        "entities": _map_entities_v3(parsed_story),
        "event_type": str(parsed_story.get("story_type") or "news").strip(),
        "quoted_statements": [],
        "field_confidences": field_confidences,
        "validation_score": confidence_score,
        "hold_for_review": confidence_score < CONFIG.Pipeline.validation_score_threshold,
        "source_count": int(cluster.get("source_count") or len(source_urls)),
        "source_urls": source_urls,
    }
    insert_extracted_story(story)
    return story


def _build_keywords_v3(parsed_article: dict, parsed_story: dict, category: str) -> list[str]:
    keywords = parsed_article.get("keywords") or [
        parsed_story.get("bike_name"),
        parsed_story.get("brand"),
        parsed_story.get("category"),
        parsed_story.get("story_type"),
        "motorcycle news",
        "bike price India",
    ]
    return [str(keyword).strip() for keyword in keywords if str(keyword).strip()][:6]


def _build_draft_article_v3(
    parsed_article: dict,
    parsed_story: dict,
    story_id: str | None,
    run_id: str,
    source_urls: list[str],
) -> dict:
    category = str(parsed_story.get("category") or parsed_story.get("story_type") or "news").strip().lower()
    if category not in ALLOWED_CATEGORIES:
        category = "news"

    title = str(parsed_article.get("title") or parsed_story.get("bike_name") or "Motorcycle update").strip()
    quality = assess_article_quality(parsed_article.get("markdown", ""))
    bike_name = str(parsed_story.get("bike_name") or title).strip()
    image_query = build_image_search_queries(bike_name)[0]

    article = {
        "article_id": str(uuid.uuid4()),
        "story_id": story_id or "fallback_story",
        "run_id": run_id,
        "title": title,
        "meta_description": _normalize_meta_description_v3(parsed_article.get("meta_description", "")),
        "slug": ensure_unique_slug(normalize_slug(parsed_article.get("slug") or title)),
        "body": quality["article"],
        "tags": _build_keywords_v3(parsed_article, parsed_story, category),
        "category": category,
        "image_prompt": image_query,
        "image_url": None,
        "image_source": None,
        "alt_text": None,
        "image_status": "pending",
        "source_urls": source_urls,
        "approval_status": "pending",
        "approved_by": None,
        "approved_at": None,
        "rejected_by": None,
        "rejected_reason": None,
        "edit_count": 0,
        "approval_expires_at": (datetime.now(timezone.utc) + timedelta(hours=CONFIG.Pipeline.approval_timeout_hours)).isoformat(),
        "scheduled_publish_at": None,
        "published_url": None,
        "image_quality_flag": "pending",
        "pipeline_stage": "draft",
    }
    insert_draft_article(article)
    article["quality_score"] = quality["score"]
    article["quality_eligible"] = quality["eligible"]
    article["buyer_relevance"] = parsed_story.get("buyer_relevance")
    return article


async def _call_story_model_v3(llm: LLMService, prompt: str, context_label: str):
    config = types.GenerateContentConfig(
        system_instruction=STORY_SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=STORY_CLUSTER_SCHEMA,
        temperature=0.25,
        max_output_tokens=3584,
    )
    return await llm.generate_content_with_usage(
        model=CONFIG.Gemini.model,
        contents=prompt,
        config=config,
        context_label=context_label,
        parse_json=True,
    )


async def _run_story_agent_v3(clusters: list[dict], run_id: str) -> dict:
    try:
        llm = LLMService()
        saved_stories = []
        saved_drafts = []
        processed_cluster_ids = []
        failed_cluster_ids = []
        seen_signatures = set()

        for cluster in clusters:
            items = _hydrate_cluster_items_v3(cluster)
            trace = AgentTrace(
                agent_name="story_agent",
                action="generate_story_cluster",
                input_summary=f"{cluster.get('canonical_topic') or 'motorcycle update'} ({len(items)} sources)",
                extra_params={
                    "run_id": run_id,
                    "cluster_id": cluster.get("cluster_id"),
                    "model": CONFIG.Gemini.model,
                },
            )

            try:
                if not items:
                    trace.status = "skipped"
                    trace.output_summary = "No source items found for cluster"
                    failed_cluster_ids.append(cluster.get("cluster_id"))
                    logger.warning("Cluster skipped without hydrated items", extra={"cluster_id": cluster.get("cluster_id")})
                    continue

                signature = _build_cluster_signature_v3(cluster, items)
                if signature in seen_signatures:
                    trace.status = "skipped"
                    trace.output_summary = "Duplicate cluster skipped in current run"
                    logger.info("Duplicate cluster skipped", extra={"cluster_id": cluster.get("cluster_id")})
                    continue
                seen_signatures.add(signature)

                await sleep(CONFIG.Gemini.rate_limit_delay_ms)
                prompt = build_story_prompt(cluster, items)
                parsed, usage = await _call_story_model_v3(llm, prompt, "story_agent")
                trace.add_usage(usage)

                source_urls = [item.get("url") for item in items if item.get("url")]
                story = _save_extracted_story_v3(parsed.get("story", {}), cluster, source_urls)
                saved_stories.append(story)

                if story.get("hold_for_review"):
                    failed_cluster_ids.append(cluster.get("cluster_id"))
                    trace.status = "skipped"
                    trace.output_summary = "Validation confidence too low for automatic publication"
                    logger.warning("Story held for review", extra={"cluster_id": cluster.get("cluster_id"), "validation_score": story.get("validation_score")})
                    continue

                draft = _build_draft_article_v3(parsed.get("article", {}), parsed.get("story", {}), story["story_id"], run_id, source_urls)
                saved_drafts.append(draft)
                processed_cluster_ids.append(cluster.get("cluster_id"))
                trace.output_summary = (
                    f"story_id={story['story_id']} draft_id={draft['article_id']} "
                    f"quality={draft.get('quality_score')} eligible={draft.get('quality_eligible')}"
                )
            except Exception as error:
                failed_cluster_ids.append(cluster.get("cluster_id"))
                trace.fail(error)
                logger.error("Story cluster failed", extra={"cluster_id": cluster.get("cluster_id"), "error": str(error)}, exc_info=True)
            finally:
                await trace.flush()

        logger.info(
            "Story agent complete",
            extra={
                "run_id": run_id,
                "clusters": len(clusters),
                "stories": len(saved_stories),
                "drafts": len(saved_drafts),
                "failed_clusters": len(failed_cluster_ids),
            },
        )
        return {
            "stories": saved_stories,
            "drafts": saved_drafts,
            "processed_cluster_ids": processed_cluster_ids,
            "failed_cluster_ids": failed_cluster_ids,
        }
    except Exception as error:
        raise handle_error(error, logger, {"agent": "story_agent", "run_id": run_id})


async def _run_fallback_story_agent_v3(run_id: str) -> list[dict]:
    try:
        llm = LLMService()
        trace = AgentTrace(
            agent_name="story_agent",
            action="generate_fallback_story",
            input_summary="fallback evergreen motorcycle article",
            extra_params={"run_id": run_id, "model": CONFIG.Gemini.model},
        )
        try:
            await sleep(CONFIG.Gemini.rate_limit_delay_ms)
            parsed, usage = await _call_story_model_v3(llm, FALLBACK_STORY_PROMPT, "story_agent_fallback")
            trace.add_usage(usage)
            draft = _build_draft_article_v3(parsed.get("article", {}), parsed.get("story", {}), None, run_id, [])
            trace.output_summary = f"fallback_draft_id={draft['article_id']} quality={draft.get('quality_score')}"
            return [draft]
        except Exception as error:
            trace.fail(error)
            raise
        finally:
            await trace.flush()
    except Exception as error:
        raise handle_error(error, logger, {"agent": "story_agent_fallback", "run_id": run_id})


async def _regenerate_article_v3(llm: LLMService, draft: dict, feedback: str) -> dict:
    prompt = "\n".join(
        [
            "You are revising an already drafted motorcycle article.",
            f"Title: {draft.get('title')}",
            f"Meta Description: {draft.get('meta_description')}",
            f"Article:\n{draft.get('body')}",
            f"Editor feedback: {feedback}",
            "Return valid JSON matching the article-only schema.",
        ]
    )
    config = types.GenerateContentConfig(
        system_instruction=STORY_SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=ARTICLE_ONLY_SCHEMA,
        temperature=0.25,
        max_output_tokens=3072,
    )

    try:
        response, _ = await llm.generate_content_with_usage(
            model=CONFIG.Gemini.model,
            contents=prompt,
            config=config,
            context_label="story_agent_regenerate",
            parse_json=True,
        )
        quality = assess_article_quality(response.get("markdown", draft.get("body", "")))
        draft["title"] = str(response.get("title") or draft.get("title")).strip()
        draft["meta_description"] = _normalize_meta_description_v3(response.get("meta_description", draft.get("meta_description")))
        draft["slug"] = normalize_slug(response.get("slug") or response.get("title") or draft.get("title"))
        draft["body"] = quality["article"]
        draft["tags"] = [str(keyword).strip() for keyword in (response.get("keywords") or draft.get("tags") or []) if str(keyword).strip()][:6]
        draft["edit_count"] = int(draft.get("edit_count", 0)) + 1
        return draft
    except Exception as error:
        logger.warning("Article regeneration failed", extra={"article_id": draft.get("article_id"), "error": str(error)})
        return draft


run_story_agent = _run_story_agent_v3
run_fallback_story_agent = _run_fallback_story_agent_v3
regenerate_article = _regenerate_article_v3
