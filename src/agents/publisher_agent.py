# FILE: src/agents/publisher_agent.py | PURPOSE: Stage 10 — publish approved articles
import os
import json
import asyncio
import httpx
import re
from html import escape
from datetime import datetime, timedelta, timezone

from src.config.config import CONFIG
from src.db.database import db
from src.db.queries.draft_articles import get_scheduled_publications, update_draft_article
from src.utils.error_handler import handle_error
from src.utils.logger import create_logger
from src.utils.observability import AgentTrace
from src.utils.sleep import sleep

logger = create_logger("publisher_agent")

def should_publish_now(now: datetime = None) -> bool:
    if now is None:
        now = datetime.now()
    hour = now.hour
    return 6 <= hour <= 22

def build_markdown_article(draft: dict, published_at: str) -> str:
    body = sanitize_article_headings(str(draft.get("body", "")), draft.get("title", ""))
    body = inject_internal_links(body, draft)

    source_urls = "\n".join(f'  - "{url}"' for url in draft.get("source_urls", []))
    tags = ", ".join(f'"{tag}"' for tag in draft.get("tags", []))
    canonical_url = build_canonical_url(draft)
    schema_json_ld = json.dumps(build_blogposting_schema(draft, published_at, canonical_url), ensure_ascii=False)
    
    return f"""---
title: "{draft.get('title')}"
slug: "{draft.get('slug')}"
meta_description: "{draft.get('meta_description')}"
category: "{draft.get('category')}"
tags: [{tags}]
image_url: "{draft.get('image_url')}"
image_alt: "{draft.get('alt_text')}"
published_at: "{published_at}"
canonical_url: "{canonical_url}"
schema_json_ld: '{schema_json_ld}'
source_urls:
{source_urls}
author: "NewsBot Editorial Team"
---

{body}
"""


def build_canonical_url(draft: dict) -> str:
    return f"{CONFIG.App.base_url.rstrip('/')}/bikes/{draft.get('slug')}"


def sanitize_article_headings(body: str, title: str) -> str:
    lines = body.splitlines()
    sanitized = []
    skip_section = False
    for line in lines:
        stripped = line.strip()
        normalized = stripped.lower().lstrip("#").strip()

        if normalized in {"table of contents", "toc", "faq", "faqs", "frequently asked questions"}:
            skip_section = True
            continue

        if skip_section and stripped.startswith("#"):
            skip_section = False

        if skip_section:
            continue

        if stripped.startswith("# "):
            # Keep a single H1 at page title level only.
            sanitized.append(f"## {stripped[2:].strip()}")
        elif stripped.startswith("####"):
            sanitized.append(f"### {stripped.lstrip('#').strip()}")
        else:
            sanitized.append(line)
    return "\n".join(sanitized).strip()


def inject_internal_links(body: str, draft: dict) -> str:
    tags = [str(tag).strip().lower().replace(" ", "-") for tag in (draft.get("tags") or []) if str(tag).strip()]
    category = str(draft.get("category") or "news").strip().lower()
    title = str(draft.get("title") or "").strip()

    related_links = []
    if category:
        related_links.append(f"- Explore more in [/{category}](/{category})")
    for tag in tags[:3]:
        related_links.append(f"- Related bikes: [/bikes/{tag}](/bikes/{tag})")

    if title:
        candidate = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        if candidate:
            related_links.append(f"- Similar story: [/bikes/{candidate}](/bikes/{candidate})")

    if not related_links:
        return body

    return body + "\n\n## Related Reading\n" + "\n".join(related_links)


def markdown_to_html(markdown_text: str) -> str:
    html_lines = []
    in_list = False
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{escape(stripped[4:])}</h3>")
            continue

        if stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{escape(stripped[3:])}</h2>")
            continue

        if stripped.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            content = escape(stripped[2:])
            content = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', content)
            html_lines.append(f"<li>{content}</li>")
            continue

        if in_list:
            html_lines.append("</ul>")
            in_list = False

        paragraph = escape(stripped)
        paragraph = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', paragraph)
        html_lines.append(f"<p>{paragraph}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def build_blogposting_schema(draft: dict, published_at: str, canonical_url: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": draft.get("title") or "",
        "description": draft.get("meta_description") or "",
        "author": "NewsBot Editorial Team",
        "datePublished": published_at,
        "image": draft.get("image_url") or "",
        "mainEntityOfPage": canonical_url,
    }


def build_html_article(draft: dict, published_at: str) -> str:
    body = sanitize_article_headings(str(draft.get("body", "")), draft.get("title", ""))
    body = inject_internal_links(body, draft)
    body_html = markdown_to_html(body)
    canonical_url = build_canonical_url(draft)
    schema_json_ld = json.dumps(build_blogposting_schema(draft, published_at, canonical_url), ensure_ascii=False)

    image_block = ""
    if draft.get("image_url"):
        image_block = (
            f'<img src="{escape(str(draft.get("image_url")))}" '
            f'alt="{escape(str(draft.get("alt_text") or draft.get("title") or "bike article image"))}" '
            'loading="lazy" decoding="async" />'
        )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(str(draft.get('title') or 'NewsBot Article'))}</title>
    <meta name="description" content="{escape(str(draft.get('meta_description') or ''))}" />
    <link rel="canonical" href="{escape(canonical_url)}" />
    <script type="application/ld+json">{schema_json_ld}</script>
  </head>
  <body>
    <article>
      <h1>{escape(str(draft.get('title') or ''))}</h1>
      {image_block}
      {body_html}
    </article>
  </body>
</html>
"""

def _sync_write_file(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

async def run_publisher_agent(draft: dict) -> dict:
    trace = AgentTrace(
        agent_name="publisher_agent",
        action="publish_article",
        input_summary=str(draft.get("title") or draft.get("article_id")),
        extra_params={"run_id": draft.get("run_id")},
    )
    try:
        now = datetime.now()
        if not should_publish_now(now):
            scheduled = now + timedelta(days=1)
            scheduled = scheduled.replace(hour=8, minute=0, second=0, microsecond=0)
            scheduled_iso = scheduled.isoformat()
            
            update_draft_article(draft["article_id"], {
                "approval_status": "approved",
                "scheduled_publish_at": scheduled_iso,
            })
            logger.info("Article scheduled for next publish window", extra={"article_id": draft["article_id"], "scheduled_at": scheduled_iso})
            trace.output_summary = f"scheduled_at={scheduled_iso}"
            return {"published_url": draft.get("published_url", "")}

        published_at = now.isoformat()
        markdown_path = os.path.join(CONFIG.Paths.articles_dir, f"{draft.get('slug')}.md")
        html_path = os.path.join(CONFIG.Paths.articles_dir, f"{draft.get('slug')}.html")
        
        await asyncio.to_thread(_sync_write_file, markdown_path, build_markdown_article(draft, published_at))
        await asyncio.to_thread(_sync_write_file, html_path, build_html_article(draft, published_at))

        published_url = build_canonical_url(draft)
        if CONFIG.Cms.webhook_url:
            payload = {
                **draft,
                "published_at": published_at,
                "markdown_path": markdown_path,
                "html_path": html_path,
                "canonical_url": build_canonical_url(draft),
                "schema": build_blogposting_schema(draft, published_at, build_canonical_url(draft)),
            }
            delays = [1000, 5000, 15000]
            last_error = None
            
            async with httpx.AsyncClient() as client:
                for delay in delays:
                    try:
                        response = await client.post(
                            CONFIG.Cms.webhook_url,
                            json=payload,
                            headers={"x-api-key": CONFIG.Cms.api_key},
                            timeout=10.0
                        )
                        response.raise_for_status()
                        response_data = response.json()
                        published_url = response_data.get("published_url", response_data.get("url", build_canonical_url(draft)))
                        last_error = None
                        break
                    except Exception as error:
                        last_error = error
                        logger.warning("CMS publish attempt failed", extra={"article_id": draft["article_id"], "delay": delay, "error": str(error)})
                        await asyncio.sleep(delay / 1000.0)
                        
            if last_error:
                logger.error("CMS publish failed after retries", extra={"article_id": draft["article_id"], "error": str(last_error)})
                return {"published_url": draft.get("published_url", "")}

        db.execute(
            """
            INSERT INTO published_slugs (slug, article_id, published_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET
              article_id = EXCLUDED.article_id,
              published_at = EXCLUDED.published_at
            """,
            (draft["slug"], draft["article_id"], published_at),
        )

        update_draft_article(draft["article_id"], {
            "approval_status": "published",
            "published_url": published_url,
            "scheduled_publish_at": None,
        })
        
        logger.info("Article published", extra={"article_id": draft["article_id"], "published_url": published_url})
        trace.output_summary = published_url
        return {"published_url": published_url}
    except Exception as error:
        trace.fail(error)
        raise handle_error(error, logger, {"agent": "publisher_agent", "article_id": draft.get("article_id")})
    finally:
        await trace.flush()

async def publish_scheduled_articles() -> int:
    try:
        due_articles = get_scheduled_publications(datetime.now().isoformat())
        for draft in due_articles:
            await run_publisher_agent(draft)
        return len(due_articles)
    except Exception as error:
        raise handle_error(error, logger, {"agent": "publisher_agent:scheduled"})
