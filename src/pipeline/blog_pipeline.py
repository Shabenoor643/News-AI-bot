# FILE: src/pipeline/blog_pipeline.py | PURPOSE: Main pipeline orchestrator
import asyncio
from datetime import datetime, timezone
import time

from src.agents.crawler_agent import run_crawler_agent
from src.agents.filter_agent import run_filter_agent
from src.agents.grouping_agent import run_grouping_agent
from src.agents.image_agent import run_image_agent
from src.agents.story_agent import run_story_agent, run_fallback_story_agent
from src.approval.approval_service import send_approval_email
from src.db.queries.story_clusters import get_clusters_by_stage, update_cluster_stage
from src.db.queries.draft_articles import get_drafts_by_stage, update_draft_stage
from src.utils.article_quality import assess_article_quality
from src.utils.error_handler import handle_error
from src.utils.logger import create_logger
from src.utils.observability import AgentTrace, count_logged_actions
from src.config.config import CONFIG

logger = create_logger("blog_pipeline")

async def run_blog_pipeline(run_id: str, trigger_type: str = "scheduled") -> dict:
    trace = AgentTrace(
        agent_name="blog_pipeline",
        action="run_pipeline",
        input_summary=trigger_type,
        extra_params={"run_id": run_id},
    )
    try:
        start_time_total = time.perf_counter()
        # Check if we should resume from a later stage
        drafts_needing_images = get_drafts_by_stage('draft')
        clusters_needing_story = get_clusters_by_stage('grouped')
        
        # Determine if we should skip crawling
        should_crawl = not (drafts_needing_images or clusters_needing_story)

        raw_items = []
        filtered_items = []
        story_result = {"drafts": [], "processed_cluster_ids": [], "failed_cluster_ids": []}
        
        if should_crawl:
            start_time_crawl = time.perf_counter()
            if trigger_type != "weekly":
                raw_items = await run_crawler_agent(run_id)
                filtered_items = await run_filter_agent(raw_items)

            if not filtered_items:
                logger.info("No relevant news found, running fallback content engine", extra={"run_id": run_id})
                await run_fallback_story_agent(run_id)
                # Fallback drafts are saved as 'draft'
            else:
                await run_grouping_agent(filtered_items, run_id)
                # clusters are saved as 'grouped'
                clusters_needing_story = get_clusters_by_stage('grouped')
            logger.info(f"Crawl and Grouping took {time.perf_counter() - start_time_crawl:.2f}s")
                
        # 1. Process Stories (Extract, Validate, Content)
        if clusters_needing_story:
            start_time_story = time.perf_counter()
            story_result = await run_story_agent(clusters_needing_story, run_id)
            
            for cluster_id in story_result.get("processed_cluster_ids", []):
                update_cluster_stage(cluster_id, 'content_written')
            logger.info(f"Story processing took {time.perf_counter() - start_time_story:.2f}s")
            
        # 2. Images remain background work so the story/email path stays non-blocking.
        drafts_needing_images = get_drafts_by_stage('draft')
        if drafts_needing_images:
            asyncio.create_task(run_image_agent(drafts_needing_images, run_id))
            
        # 3. Approval Emails - send only to top quality articles and never exceed daily cap
        start_time_approval = time.perf_counter()
        today = datetime.now(timezone.utc).date().isoformat()
        sent_today = count_logged_actions("email_service", "send_email", today)
        remaining_budget = max(0, min(CONFIG.Email.daily_limit, CONFIG.Pipeline.max_approval_emails) - sent_today)

        drafts_ranked = []
        for draft in drafts_needing_images:
            quality = assess_article_quality(str(draft.get("body", "")))
            if quality["eligible"]:
                draft["quality_score"] = quality["score"]
                drafts_ranked.append(draft)

        drafts_ranked = sorted(
            drafts_ranked,
            key=lambda draft: (draft.get("quality_score", 0), len(str(draft.get("body", "")).split())),
            reverse=True,
        )
        drafts_needing_approval = drafts_ranked[:remaining_budget]
        if len(drafts_ranked) > remaining_budget:
            logger.info(
                "Approval email cap applied",
                extra={
                    "eligible_candidates": len(drafts_ranked),
                    "selected": len(drafts_needing_approval),
                    "cap": remaining_budget,
                    "sent_today": sent_today,
                },
            )
        emailed_count = 0
        for draft in drafts_needing_approval:
            try:
                email_sent = await send_approval_email(draft)
                if email_sent:
                    update_draft_stage(draft['article_id'], 'approval_sent')
                    emailed_count += 1
                    logger.info(f"Approval email sent for article: {draft['article_id']}")
                else:
                    logger.info(f"Approval email skipped for article: {draft['article_id']}")
            except Exception as e:
                logger.error(f"Failed to send approval email for {draft['article_id']}: {e}")
        logger.info(f"Sent {emailed_count} individual approval emails in {time.perf_counter() - start_time_approval:.2f}s")

        summary = {
            "run_id": run_id,
            "items_fetched": len(raw_items),
            "items_passed_filter": len(filtered_items),
            "articles_generated": len(drafts_needing_images),
            "story_failures": len(story_result.get("failed_cluster_ids", [])),
            "status": "awaiting_approval",
            "total_time_seconds": round(time.perf_counter() - start_time_total, 2)
        }

        logger.info("Pipeline complete", extra=summary)
        trace.output_summary = (
            f"generated={summary['articles_generated']} emailed={emailed_count} total_time={summary['total_time_seconds']}"
        )
        return summary
    except Exception as error:
        trace.fail(error)
        raise handle_error(error, logger, {"agent": "blog_pipeline", "run_id": run_id})
    finally:
        await trace.flush()
