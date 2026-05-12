# FILE: src/db/queries/job_registry.py | PURPOSE: CRUD helpers for job_registry records
from src.db.database import db
from src.utils.error_handler import DBError, handle_error
from src.utils.logger import create_logger

logger = create_logger("queries:job_registry")

def create_job_entry(run_id: str, trigger_type: str) -> None:
    try:
        query = """
          INSERT INTO job_registry (run_id, triggered_at, trigger_type, status)
          VALUES (%s, NOW(), %s, 'running')
        """
        db.execute(query, (run_id, trigger_type))
    except Exception as error:
        raise handle_error(DBError("Failed to create job entry", {"run_id": run_id, "error": str(error)}), logger, {"run_id": run_id})

def update_job_status(run_id: str, status: str, fields: dict = None) -> None:
    fields = fields or {}
    payload = {"run_id": run_id, "status": status, **fields}
    entries = {k: v for k, v in payload.items() if k != "run_id" and v is not None}
    
    assignments = [f"{k} = %({k})s" for k in entries.keys()]
    query = f"UPDATE job_registry SET {', '.join(assignments)} WHERE run_id = %(run_id)s"
    
    db.execute(query, payload)

def get_active_run() -> dict | None:
    query = "SELECT * FROM job_registry WHERE status = 'running' ORDER BY triggered_at DESC LIMIT 1"
    row = db.execute(query).fetchone()
    return dict(row) if row else None

def acquire_pipeline_lock() -> bool:
    """Returns True if lock was acquired, False if already running."""
    query = "SELECT COUNT(*) FROM job_registry WHERE status = 'running' AND triggered_at > NOW() - INTERVAL '2 hours'"
    active_count = db.execute(query).fetchone()[0]
    return active_count == 0

def is_pipeline_locked() -> bool:
    query = "SELECT COUNT(*) FROM job_registry WHERE status = 'running' AND triggered_at > NOW() - INTERVAL '2 hours'"
    return db.execute(query).fetchone()[0] > 0
