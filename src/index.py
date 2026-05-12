# FILE: src/index.py | PURPOSE: Application entry point
import os
import sys
import asyncio
from dotenv import load_dotenv

# Load env before imports
load_dotenv()

from src.db.database import init_db
from src.pipeline.pipeline_runner import start_scheduler, trigger_run
from src.utils.logger import create_logger

logger = create_logger("index")

async def main():
    logger.info("🏍️  NewsBot Blogs starting up...")

    init_db()

    if "--run-now" in sys.argv:
        logger.info("Manual run triggered via --run-now flag")
        await trigger_run("manual")

    start_scheduler()

    port = int(os.getenv("PORT", "3001"))
    logger.info(f"NewsBot Blogs is running. Approval server on port {port}")
    
    import uvicorn
    from src.approval.approval_server import app
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as err:
        logger.error(f"Fatal startup error: {err}", exc_info=True)
        sys.exit(1)
