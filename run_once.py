import asyncio
import uuid
from dotenv import load_dotenv
load_dotenv()

from src.db.database import init_db
from src.pipeline.blog_pipeline import run_blog_pipeline
from src.db.queries.job_registry import create_job_entry

async def main():
    print("Initializing DB...")
    init_db()
    run_id = str(uuid.uuid4())
    print(f"Running pipeline now... run_id={run_id}")
    create_job_entry(run_id, "manual")
    await run_blog_pipeline(run_id, "manual")
    print("Run completed.")

if __name__ == "__main__":
    asyncio.run(main())