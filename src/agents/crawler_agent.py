# FILE: src/agents/crawler_agent.py | PURPOSE: Stage 2 — news crawl via Gemini Search grounding
import os
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

from src.config.config import CONFIG
from src.db.queries.raw_items import insert_raw_item, url_hash_exists
from src.utils.error_handler import GeminiInputError, handle_error
from src.utils.logger import create_logger
from src.utils.parse_gemini_json import parse_gemini_json
from src.utils.sleep import sleep
from src.utils.llm_service import LLMService

logger = create_logger("crawler_agent")


def _get_crawl_date_window() -> tuple[datetime, datetime]:
    now_utc = datetime.now(timezone.utc)

    # Explicit date override is useful for backfills.
    if CONFIG.Pipeline.crawl_start_date and CONFIG.Pipeline.crawl_end_date:
        start_dt = datetime.combine(CONFIG.Pipeline.crawl_start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(CONFIG.Pipeline.crawl_end_date, datetime.max.time(), tzinfo=timezone.utc)
        return start_dt, end_dt

    lookback_days = max(1, CONFIG.Pipeline.lookback_window_days)
    return now_utc - timedelta(days=lookback_days), now_utc

def build_crawler_queries() -> list[str]:
    current_year = datetime.now().year
    return [
        f"India two-wheeler news motorcycle launch {current_year} price specs",
        "India electric two-wheeler EV scooter launch review",
        "India motorcycle recall safety alert two-wheeler",
        "India premium motorcycle and scooter price update",
        "India bike industry sales and policy news two wheeler",
    ]

def normalize_crawler_items(run_id: str, query: str, items: list[dict]) -> list[dict]:
    normalized_items = []
    for item in items:
        normalized_url = str(item.get("url", "")).strip()
        hostname = normalized_url.split('/')[2] if "://" in normalized_url else f"search:{query}"
        title = str(item.get("title", "")).strip()
        snippet = str(item.get("snippet", "")).strip()
        
        if title and normalized_url and snippet:
            url_hash = hashlib.sha256(normalized_url.encode('utf-8')).hexdigest()
            normalized_items.append({
                "item_id": str(uuid.uuid4()),
                "run_id": run_id,
                "source_id": hostname,
                "title": title,
                "url": normalized_url,
                "url_hash": url_hash,
                "published_at": item.get("published_at"),
                "snippet": snippet,
                "full_text": None,
                "language": "en",
                "full_text_available": 0,
                "relevance_score": 0.0,
                "status": "pending",
            })
    return normalized_items

async def call_crawler(llm: LLMService, query: str):
    window_start, window_end = _get_crawl_date_window()
    start_label = window_start.strftime('%B %d, %Y')
    end_label = window_end.strftime('%B %d, %Y')
    
    prompt = f"""Today's date is {end_label}. Find the 5 most recent and specific news items for: "{query}". Focus on India two-wheeler market only. For each item return: title, URL, published date, and a 2-3 sentence summary. ONLY return news published between {start_label} and {end_label}. Do NOT return old news.

You MUST return the result EXACTLY as a JSON block. If no relevant news is found at all, return an empty items list.
```json
{{
  "items": [
    {{
      "title": "string",
      "url": "string",
      "published_at": "string",
      "snippet": "string"
    }}
  ]
}}
```"""
    
    return await llm.generate_content(
        model=CONFIG.Gemini.model,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}]
        )
    )

async def run_crawler_agent(run_id: str) -> list[dict]:
    try:
        llm = LLMService()
        search_queries = build_crawler_queries()
        raw_items = []

        for query in search_queries:
            await sleep(CONFIG.Gemini.rate_limit_delay_ms)
            try:
                response = await call_crawler(llm, query)
                parsed = parse_gemini_json(response.text, "crawler_agent")
                
                fallback_urls = []
                if response.candidates and response.candidates[0].grounding_metadata and response.candidates[0].grounding_metadata.grounding_chunks:
                    for chunk in response.candidates[0].grounding_metadata.grounding_chunks:
                        if chunk.web and chunk.web.uri:
                            fallback_urls.append(chunk.web.uri)
                
                parsed_items = parsed.get("items", [])
                mapped_items = []
                for i, item in enumerate(parsed_items):
                    url = item.get("url") or (fallback_urls[i] if i < len(fallback_urls) else "")
                    mapped_items.append({**item, "url": url})
                    
                normalized_items = normalize_crawler_items(run_id, query, mapped_items)

                window_start, window_end = _get_crawl_date_window()
                
                filtered_items = []
                for item in normalized_items:
                    if not item.get("published_at"):
                        continue
                    try:
                        from dateutil import parser
                        published = parser.parse(item["published_at"])
                        if published.tzinfo is None:
                            published = published.replace(tzinfo=timezone.utc)
                        if window_start <= published <= window_end:
                            filtered_items.append(item)
                    except Exception:
                        pass

                for item in filtered_items:
                    if not url_hash_exists(item["url_hash"]):
                        insert_raw_item(item)
                        raw_items.append(item)
            except Exception as error:
                handle_error(error, logger, {"agent": "crawler_agent", "run_id": run_id, "query": query})

        logger.info("Crawler complete", extra={"run_id": run_id, "total_items": len(raw_items)})
        return raw_items
    except Exception as error:
        raise handle_error(error, logger, {"agent": "crawler_agent", "run_id": run_id})
