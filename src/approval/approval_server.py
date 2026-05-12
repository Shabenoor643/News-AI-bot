# FILE: src/approval/approval_server.py | PURPOSE: FastAPI server for approval callbacks
import os
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Response, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
import uvicorn

from src.approval.approval_service import approve_article, is_valid_approval_token, reject_article, request_article_edit
from src.db.queries.draft_articles import get_draft_by_article_id, update_draft_article
from src.utils.error_handler import handle_error
from src.utils.logger import create_logger
from src.config.config import CONFIG

logger = create_logger("approval_server")

app = FastAPI()

def render_page(title: str, message: str) -> str:
    return f"""
    <html>
      <head><title>{title}</title></head>
      <body style="font-family:Arial,sans-serif;max-width:640px;margin:40px auto;line-height:1.6;">
        <h1>{title}</h1>
        <p>{message}</p>
      </body>
    </html>
    """

async def _retry_image_background(draft: dict):
    try:
        from src.agents.image_agent import run_image_agent
        from src.approval.approval_service import send_approval_email
        from src.db.queries.draft_articles import update_draft_stage
        
        await run_image_agent([draft], draft.get("run_id"))
        updated_draft = get_draft_by_article_id(draft["article_id"])
        email_sent = await send_approval_email(updated_draft)
        if email_sent:
            update_draft_stage(draft['article_id'], 'approval_sent')
    except Exception as e:
        logger.error(f"Background retry image failed: {e}")

@app.get("/approve/{article_id}", response_class=HTMLResponse)
async def handle_approval_callback(article_id: str, request: Request, background_tasks: BackgroundTasks, token: str = None, action: str = None, approverEmail: str = ""):
    try:
        draft = get_draft_by_article_id(article_id)
        if not draft:
            return HTMLResponse(render_page("Article not found", "The requested article could not be found."), status_code=404)
            
        if draft.get("approval_status") != "pending" and action != "retry_image":
            return HTMLResponse(render_page("Already processed", f"This article is already {draft.get('approval_status')}."), status_code=400)
            
        expires_at = draft.get("approval_expires_at")
        if expires_at:
            # Handle ISO formats that might end with Z
            expires_at = expires_at.replace("Z", "+00:00")
            if datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc):
                return HTMLResponse(render_page("Approval expired", "This approval link has expired."), status_code=410)
                
        if not token or not is_valid_approval_token(draft, token):
            return HTMLResponse(render_page("Invalid token", "This approval token is invalid."), status_code=403)

        if action == "approve":
            await approve_article(article_id, approverEmail)
            return HTMLResponse(render_page("Article approved", "Article approved successfully. It will publish immediately or at the next allowed publish window."))
            
        if action == "reject":
            await reject_article(article_id, "Rejected via approval link", approverEmail)
            return HTMLResponse(render_page("Article rejected", "The article was rejected."))
            
        if action == "retry_image":
            update_draft_article(article_id, {
                "pipeline_stage": "draft",
                "image_quality_flag": "ok",
                "approval_status": "pending" # Reset back to pending so that the token works again
            })
            updated_draft = get_draft_by_article_id(article_id)
            background_tasks.add_task(_retry_image_background, updated_draft)
            return HTMLResponse(render_page("Image Retry Started", "The image generation has been reset and is retrying in the background. You will receive a new email shortly."), status_code=202)

        if action == "edit":
            return HTMLResponse(f"""
                <html>
                  <body style="font-family:Arial,sans-serif;max-width:640px;margin:40px auto;">
                    <h1>Request Edit</h1>
                    <form method="post" action="/approve/{article_id}/edit-submit">
                      <input type="hidden" name="token" value="{token}" />
                      <label>Email</label><br />
                      <input type="email" name="editorEmail" value="{approverEmail}" style="width:100%;padding:8px;" /><br /><br />
                      <label>Edit notes</label><br />
                      <textarea name="notes" rows="8" style="width:100%;padding:8px;"></textarea><br /><br />
                      <button type="submit">Submit edit request</button>
                    </form>
                  </body>
                </html>
            """)

        return HTMLResponse(render_page("Unknown action", "The requested action is not supported."), status_code=400)
    except Exception as error:
        normalized = handle_error(error, logger, {"route": "GET /approve/{article_id}"})
        return HTMLResponse(render_page("Approval error", normalized.args[0]), status_code=500)

@app.post("/approve/{article_id}/edit-submit", response_class=HTMLResponse)
async def handle_edit_submit(article_id: str, token: str = Form(...), editorEmail: str = Form(""), notes: str = Form("Edit requested")):
    try:
        draft = get_draft_by_article_id(article_id)
        if not draft or not token or not is_valid_approval_token(draft, token):
            return HTMLResponse(render_page("Invalid request", "The edit request token is invalid."), status_code=403)

        await request_article_edit(article_id, notes, editorEmail)
        return HTMLResponse(render_page("Edit requested", "Your edit request has been recorded."))
    except Exception as error:
        normalized = handle_error(error, logger, {"route": "POST /approve/{article_id}/edit-submit"})
        return HTMLResponse(render_page("Edit error", normalized.args[0]), status_code=500)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/bikes/{slug}", response_class=HTMLResponse)
async def serve_published_article(slug: str):
    article_path = os.path.join(CONFIG.Paths.articles_dir, f"{slug}.html")
    if not os.path.exists(article_path):
        return HTMLResponse(render_page("Not found", "Article does not exist."), status_code=404)
    with open(article_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

def start_approval_server(port: int = None):
    if port is None:
        port = CONFIG.App.port
    logger.info("Approval server starting", extra={"port": port})
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    start_approval_server()
