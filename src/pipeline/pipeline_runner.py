# FILE: src/pipeline/pipeline_runner.py | PURPOSE: APScheduler trigger + run guard
import uuid
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.config.config import CONFIG
from src.approval.approval_service import check_approval_timeouts
from src.agents.publisher_agent import publish_scheduled_articles
from src.pipeline.blog_pipeline import run_blog_pipeline
from src.utils.logger import create_logger
from src.utils.observability import AgentTrace

logger = create_logger("pipeline_runner")
scheduler = AsyncIOScheduler()

# Queue to handle pipeline triggers sequentially
pipeline_queue = asyncio.Queue()

async def pipeline_worker():
    while True:
        trigger_type = await pipeline_queue.get()
        run_id = str(uuid.uuid4())
        trace = AgentTrace(
            agent_name="pipeline_runner",
            action="pipeline_worker",
            input_summary=trigger_type,
            extra_params={"run_id": run_id},
        )
        try:
            logger.info("Pipeline triggered", extra={"run_id": run_id, "trigger_type": trigger_type})
            await run_blog_pipeline(run_id, trigger_type)
            trace.output_summary = "completed"
        except Exception as e:
            trace.fail(e)
            logger.error(f"Pipeline run failed: {e}", exc_info=True)
        finally:
            await trace.flush()
            pipeline_queue.task_done()

async def trigger_run(trigger_type: str = "scheduled") -> None:
    await pipeline_queue.put(trigger_type)
    logger.info(f"Queued pipeline run: {trigger_type}")

async def _scheduled_trigger_run(trigger_type: str):
    try:
        await trigger_run(trigger_type)
    except Exception as error:
        logger.error(f"Scheduled run ({trigger_type}) failed", exc_info=True)

async def _scheduled_check_timeouts():
    try:
        await check_approval_timeouts()
        await publish_scheduled_articles()
    except Exception as error:
        logger.error("Scheduled check failed", exc_info=True)

def start_scheduler() -> None:
    # Start the background worker for the pipeline queue
    asyncio.create_task(pipeline_worker())

    # 1. DAILY PIPELINE (every 6 hrs)
    scheduler.add_job(_scheduled_trigger_run, 'cron', hour='*/6', args=["daily"])
    
    # 2. WEEKLY PIPELINE (Sunday morning at 8:00 AM)
    scheduler.add_job(_scheduled_trigger_run, 'cron', day_of_week='sun', hour=8, args=["weekly"])

    # Hourly checks
    scheduler.add_job(_scheduled_check_timeouts, 'cron', minute=0)
    scheduler.start()
    logger.info("Scheduler started with Daily and Weekly pipelines")
