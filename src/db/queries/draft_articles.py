# FILE: src/db/queries/draft_articles.py | PURPOSE: CRUD helpers for draft_articles records
import json
from src.db.database import db
from src.utils.error_handler import DBError, handle_error
from src.utils.logger import create_logger

logger = create_logger("queries:draft_articles")

def insert_draft_article(draft: dict) -> None:
    try:
        query = """
          INSERT INTO draft_articles (
            article_id, story_id, run_id, title, meta_description, slug, body, tags, category,
            image_prompt, image_url, image_source, alt_text, image_status, source_urls,
            approval_status, approved_by, approved_at, rejected_by, rejected_reason,
            edit_count, approval_expires_at, scheduled_publish_at, published_url,
            image_quality_flag, pipeline_stage, vision_analysis_json
          ) VALUES (
            %(article_id)s, %(story_id)s, %(run_id)s, %(title)s, %(meta_description)s, %(slug)s, %(body)s, %(tags)s, %(category)s,
            %(image_prompt)s, %(image_url)s, %(image_source)s, %(alt_text)s, %(image_status)s, %(source_urls)s,
            %(approval_status)s, %(approved_by)s, %(approved_at)s, %(rejected_by)s, %(rejected_reason)s,
            %(edit_count)s, %(approval_expires_at)s, %(scheduled_publish_at)s, %(published_url)s,
            %(image_quality_flag)s, %(pipeline_stage)s, %(vision_analysis_json)s
          )
        """
        db.execute(query, _serialize_draft(draft))
    except Exception as error:
        raise handle_error(DBError("Failed to insert draft article", {"article_id": draft.get("article_id"), "error": str(error)}), logger, {"article_id": draft.get("article_id")})

def update_draft_article(article_id: str, fields: dict) -> None:
    entries = {k: v for k, v in fields.items() if v is not None}
    if not entries:
        return

    assignments = [f"{k} = %({k})s" for k in entries.keys()]
    query = f"UPDATE draft_articles SET {', '.join(assignments)}, updated_at = NOW() WHERE article_id = %(article_id)s"
    
    payload = {"article_id": article_id}
    for k, v in entries.items():
        payload[k] = json.dumps(v) if k in ["tags", "source_urls"] else v
        
    db.execute(query, payload)

def get_draft_by_article_id(article_id: str) -> dict | None:
    query = "SELECT * FROM draft_articles WHERE article_id = %s LIMIT 1"
    row = db.execute(query, (article_id,)).fetchone()
    return _deserialize_draft(dict(row)) if row else None

def get_pending_approvals() -> list[dict]:
    query = "SELECT * FROM draft_articles WHERE approval_status = 'pending' ORDER BY created_at ASC"
    return [_deserialize_draft(dict(row)) for row in db.execute(query).fetchall()]

def get_expired_approvals(cutoff_time: str) -> list[dict]:
    query = "SELECT * FROM draft_articles WHERE approval_status = 'pending' AND approval_expires_at <= %s ORDER BY approval_expires_at ASC"
    return [_deserialize_draft(dict(row)) for row in db.execute(query, (cutoff_time,)).fetchall()]

def get_scheduled_publications(cutoff_time: str) -> list[dict]:
    query = "SELECT * FROM draft_articles WHERE approval_status = 'approved' AND scheduled_publish_at IS NOT NULL AND scheduled_publish_at <= %s ORDER BY scheduled_publish_at ASC"
    return [_deserialize_draft(dict(row)) for row in db.execute(query, (cutoff_time,)).fetchall()]

def get_draft_by_story_id(story_id: str) -> dict | None:
    query = "SELECT * FROM draft_articles WHERE story_id = %s LIMIT 1"
    row = db.execute(query, (story_id,)).fetchone()
    return _deserialize_draft(dict(row)) if row else None

def slug_exists(slug: str) -> bool:
    query = "SELECT 1 FROM draft_articles WHERE slug = %s LIMIT 1"
    return bool(db.execute(query, (slug,)).fetchone())

def get_drafts_by_stage(stage: str) -> list[dict]:
    query = "SELECT * FROM draft_articles WHERE pipeline_stage = %s"
    return [_deserialize_draft(dict(row)) for row in db.execute(query, (stage,)).fetchall()]

def update_draft_stage(draft_id: str, stage: str) -> None:
    query = "UPDATE draft_articles SET pipeline_stage = %s, updated_at = NOW() WHERE article_id = %s"
    db.execute(query, (stage, draft_id))

def _serialize_draft(draft: dict) -> dict:
    payload = {**draft}
    payload["tags"] = json.dumps(draft.get("tags", []))
    payload["source_urls"] = json.dumps(draft.get("source_urls", []))
    for key in ["image_prompt", "image_url", "image_source", "alt_text", "image_status", "approved_by", "approved_at", "rejected_by", "rejected_reason", "approval_expires_at", "scheduled_publish_at", "published_url", "title", "meta_description", "slug", "body", "category", "article_type", "parent_story_id", "seo_score", "vision_analysis_json"]:
        if key not in payload:
            payload[key] = None
    if "edit_count" not in payload:
        payload["edit_count"] = 0
    if "approval_status" not in payload:
        payload["approval_status"] = "pending"
    if "image_quality_flag" not in payload:
        payload["image_quality_flag"] = "ok"
    if "pipeline_stage" not in payload:
        payload["pipeline_stage"] = "draft"
    return payload

def _deserialize_draft(row: dict) -> dict:
    row["tags"] = json.loads(row["tags"]) if row.get("tags") and isinstance(row["tags"], str) else (row.get("tags") or [])
    row["source_urls"] = json.loads(row["source_urls"]) if row.get("source_urls") and isinstance(row["source_urls"], str) else (row.get("source_urls") or [])
    return row
