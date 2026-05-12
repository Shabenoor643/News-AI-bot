# FILE: src/approval/approval_service.py | PURPOSE: Stage 9 — approval email workflow
import os
import hashlib
from datetime import datetime, timezone

from src.config.config import CONFIG
from src.db.queries.draft_articles import get_draft_by_article_id, get_expired_approvals, update_draft_article
from src.utils.article_quality import assess_article_quality
from src.utils.emailer import send_mail
from src.utils.error_handler import handle_error
from src.utils.logger import create_logger
from src.agents.publisher_agent import markdown_to_html, run_publisher_agent, sanitize_article_headings

logger = create_logger("approval_service")

def build_approval_token(article_id: str, expires_at: str) -> str:
    data = f"{article_id}{CONFIG.App.approval_secret}{expires_at}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()

def is_valid_approval_token(draft: dict, token: str) -> bool:
    return build_approval_token(draft.get("article_id"), draft.get("approval_expires_at")) == token

def build_approval_email_html(draft: dict) -> str:
    approval_token = build_approval_token(draft.get("article_id"), draft.get("approval_expires_at"))
    body_content = markdown_to_html(sanitize_article_headings(str(draft.get("body", "")), draft.get("title", "")))
    base = f"{CONFIG.App.base_url}/approve/{draft.get('article_id')}?token={approval_token}"

    image_block = ""
    image_path = draft.get("image_url")
    if image_path:
        image_block = (
            f'<p style="margin:12px 0 20px;">'
            f'<a href="{image_path}" style="color:#166534;text-decoration:none;font-weight:600;">View image</a>'
            f"</p>"
        )

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:760px;margin:0 auto;line-height:1.6;color:#111827;">
      <h1 style="margin:0 0 12px;">{draft.get('title')}</h1>
      <p style="margin:0 0 18px;color:#4b5563;">{draft.get('meta_description')}</p>
      {image_block}
      <div>{body_content}</div>
      <div style="display:flex;gap:12px;margin-top:24px;">
        <a href="{base}&action=approve" style="padding:10px 14px;background:#16a34a;color:#fff;text-decoration:none;border-radius:8px;">Approve</a>
        <a href="{base}&action=reject" style="padding:10px 14px;background:#dc2626;color:#fff;text-decoration:none;border-radius:8px;">Reject</a>
        <a href="{base}&action=edit" style="padding:10px 14px;background:#2563eb;color:#fff;text-decoration:none;border-radius:8px;">Request edit</a>
        <a href="{base}&action=retry_image" style="padding:10px 14px;background:#9333ea;color:#fff;text-decoration:none;border-radius:8px;">Retry image</a>
      </div>
    </div>
    """

def build_approval_email_text(draft: dict) -> str:
    body = sanitize_article_headings(str(draft.get("body", "")), draft.get("title", ""))
    return f"{draft.get('title')}\n\n{body}\n\nImage: {draft.get('image_url') or 'Pending'}"

async def send_approval_email(draft: dict) -> bool:
    if not draft:
        return False
    quality = assess_article_quality(str(draft.get("body", "")))
    if not quality["eligible"]:
        logger.info(
            "Approval email skipped for low-quality draft",
            extra={"article_id": draft.get("article_id"), "quality_score": quality["score"]},
        )
        return False
    try:
        await send_mail({
            "from": CONFIG.App.approver_emails[0] if CONFIG.App.approver_emails else os.getenv("SMTP_USER", ""),
            "to": ", ".join(CONFIG.App.approver_emails),
            "subject": f"🚀 New Bike Update: {draft.get('title')}",
            "html": build_approval_email_html(draft),
            "text": build_approval_email_text(draft),
        })
        logger.info(f"Approval email sent successfully for article: {draft.get('article_id')}")
        return True
    except Exception as error:
        raise handle_error(error, logger, {"agent": "approval_service:send", "article_id": draft.get("article_id")})

async def approve_article(article_id: str, approver_email: str) -> None:
    try:
        update_draft_article(article_id, {
            "approval_status": "approved",
            "approved_by": approver_email,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "rejected_by": None,
            "rejected_reason": None,
        })
        draft = get_draft_by_article_id(article_id)
        if draft:
            updated_draft = draft
            if draft.get("image_status") != "ready" or not draft.get("image_url"):
                from src.agents.image_agent import run_image_agent
                await run_image_agent([draft], draft.get("run_id"))
                updated_draft = get_draft_by_article_id(article_id)
            await run_publisher_agent(updated_draft)
    except Exception as error:
        raise handle_error(error, logger, {"agent": "approval_service:approve", "article_id": article_id, "approver_email": approver_email})

async def reject_article(article_id: str, reason: str, rejected_by: str = "reviewer") -> None:
    try:
        update_draft_article(article_id, {
            "approval_status": "rejected",
            "rejected_by": rejected_by,
            "rejected_reason": reason,
        })
    except Exception as error:
        raise handle_error(error, logger, {"agent": "approval_service:reject", "article_id": article_id})

async def request_article_edit(article_id: str, notes: str, requested_by: str) -> None:
    try:
        from src.agents.story_agent import regenerate_article
        from src.utils.llm_service import LLMService
        
        draft = get_draft_by_article_id(article_id)
        if not draft:
            logger.error(f"Draft not found for edit request: {article_id}")
            return
            
        # Update status to edit_requested
        update_draft_article(article_id, {
            "approval_status": "edit_requested",
            "rejected_by": requested_by,
            "rejected_reason": notes,
            "edit_count": int(draft.get("edit_count", 0)) + 1,
        })
        
        # Regenerate article based on feedback
        logger.info(f"Regenerating article {article_id} based on feedback: {notes}")
        llm = LLMService()
        updated_draft = await regenerate_article(llm, draft, notes)
        
        # Save the regenerated article
        update_draft_article(article_id, {
            "title": updated_draft.get("title"),
            "meta_description": updated_draft.get("meta_description"),
            "slug": updated_draft.get("slug"),
            "body": updated_draft.get("body"),
            "tags": updated_draft.get("tags"),
            "approval_status": "pending",  # Reset to pending for re-approval
            "pipeline_stage": "draft",
        })
        
        # Re-send approval email with updated article
        refreshed_draft = get_draft_by_article_id(article_id)
        email_sent = await send_approval_email(refreshed_draft)
        if email_sent:
            update_draft_article(article_id, {"pipeline_stage": "approval_sent"})
            logger.info(f"Article {article_id} regenerated and re-sent for approval")
        else:
            logger.info(f"Article {article_id} regenerated but held back from email due to quality gate")
        
    except Exception as error:
        raise handle_error(error, logger, {"agent": "approval_service:edit", "article_id": article_id})

async def check_approval_timeouts() -> int:
    try:
        expired = get_expired_approvals(datetime.now(timezone.utc).isoformat())
        for draft in expired:
            update_draft_article(draft["article_id"], {
                "approval_status": "archived",
                "rejected_reason": "Approval window expired",
            })
        logger.info("Approval timeout check complete", extra={"expired": len(expired)})
        return len(expired)
    except Exception as error:
        raise handle_error(error, logger, {"agent": "approval_service:timeout"})
