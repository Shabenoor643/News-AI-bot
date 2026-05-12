# FILE: src/db/queries/raw_items.py | PURPOSE: CRUD helpers for raw_items records
from src.db.database import db
from src.utils.error_handler import DBError, handle_error
from src.utils.logger import create_logger

logger = create_logger("queries:raw_items")

def insert_raw_item(item: dict) -> None:
    try:
        query = """
          INSERT INTO raw_items (
            item_id, run_id, source_id, title, url, url_hash, published_at, snippet,
            full_text, language, full_text_available, relevance_score, status
          ) VALUES (
            %(item_id)s, %(run_id)s, %(source_id)s, %(title)s, %(url)s, %(url_hash)s, %(published_at)s, %(snippet)s,
            %(full_text)s, %(language)s, %(full_text_available)s, %(relevance_score)s, %(status)s
          )
        """
        # Set missing optional fields to None
        for key in ["published_at", "snippet", "full_text"]:
            if key not in item:
                item[key] = None
        if "language" not in item: item["language"] = "en"
        if "full_text_available" not in item: item["full_text_available"] = 0
        if "relevance_score" not in item: item["relevance_score"] = 0.0
        if "status" not in item: item["status"] = "pending"

        db.execute(query, item)
    except Exception as error:
        raise handle_error(DBError("Failed to insert raw item", {"item_id": item.get("item_id"), "error": str(error)}), logger, {"item_id": item.get("item_id")})

def url_hash_exists(url_hash: str) -> bool:
    query = "SELECT 1 FROM raw_items WHERE url_hash = %s LIMIT 1"
    result = db.execute(query, (url_hash,)).fetchone()
    return bool(result)

def get_raw_items_by_run(run_id: str) -> list[dict]:
    query = "SELECT * FROM raw_items WHERE run_id = %s ORDER BY created_at ASC"
    return [dict(row) for row in db.execute(query, (run_id,)).fetchall()]

def get_raw_items_by_ids(item_ids: list[str]) -> list[dict]:
    if not item_ids:
        return []
    query = "SELECT * FROM raw_items WHERE item_id = ANY(%s) ORDER BY created_at ASC"
    return [dict(row) for row in db.execute(query, (item_ids,)).fetchall()]

def update_raw_item_score(item_id: str, score: float, status: str) -> None:
    query = "UPDATE raw_items SET relevance_score = %s, status = %s WHERE item_id = %s"
    db.execute(query, (score, status, item_id))

def update_raw_item_content(item_id: str, full_text: str, full_text_available: bool, language: str) -> None:
    query = "UPDATE raw_items SET full_text = %s, full_text_available = %s, language = %s WHERE item_id = %s"
    db.execute(query, (full_text, int(full_text_available), language, item_id))
