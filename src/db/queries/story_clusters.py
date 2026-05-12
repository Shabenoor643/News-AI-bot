# FILE: src/db/queries/story_clusters.py | PURPOSE: CRUD helpers for story_clusters and extracted_stories records
import json
from src.db.database import db
from src.utils.error_handler import DBError, handle_error
from src.utils.logger import create_logger

logger = create_logger("queries:story_clusters")

def insert_story_cluster(cluster: dict) -> None:
    try:
        query = """
          INSERT INTO story_clusters (cluster_id, run_id, canonical_topic, source_count, low_confidence, item_ids, pipeline_stage)
          VALUES (%(cluster_id)s, %(run_id)s, %(canonical_topic)s, %(source_count)s, %(low_confidence)s, %(item_ids)s, %(pipeline_stage)s)
        """
        payload = {**cluster}
        if not isinstance(payload.get("item_ids"), str):
            payload["item_ids"] = json.dumps(payload.get("item_ids", []))
        payload["low_confidence"] = int(bool(payload.get("low_confidence")))
        if "pipeline_stage" not in payload:
            payload["pipeline_stage"] = "grouped"
        db.execute(query, payload)
    except Exception as error:
        raise handle_error(DBError("Failed to insert story cluster", {"cluster_id": cluster.get("cluster_id"), "error": str(error)}), logger, {"cluster_id": cluster.get("cluster_id")})

def get_clusters_by_stage(stage: str) -> list[dict]:
    query = "SELECT * FROM story_clusters WHERE pipeline_stage = %s ORDER BY created_at ASC"
    rows = [dict(row) for row in db.execute(query, (stage,)).fetchall()]
    for row in rows:
        row["item_ids"] = json.loads(row["item_ids"]) if row.get("item_ids") and isinstance(row["item_ids"], str) else (row.get("item_ids") or [])
    return rows

def update_cluster_stage(cluster_id: str, stage: str) -> None:
    query = "UPDATE story_clusters SET pipeline_stage = %s WHERE cluster_id = %s"
    db.execute(query, (stage, cluster_id))

def get_clusters_by_run(run_id: str) -> list[dict]:
    query = "SELECT * FROM story_clusters WHERE run_id = %s ORDER BY created_at ASC"
    rows = [dict(row) for row in db.execute(query, (run_id,)).fetchall()]
    for row in rows:
        row["item_ids"] = json.loads(row["item_ids"]) if row.get("item_ids") and isinstance(row["item_ids"], str) else (row.get("item_ids") or [])
    return rows

def get_cluster_with_items(cluster_id: str) -> dict | None:
    query = "SELECT * FROM story_clusters WHERE cluster_id = %s LIMIT 1"
    row = db.execute(query, (cluster_id,)).fetchone()
    if row:
        row_dict = dict(row)
        row_dict["item_ids"] = json.loads(row_dict["item_ids"]) if row_dict.get("item_ids") and isinstance(row_dict["item_ids"], str) else (row_dict.get("item_ids") or [])
        return row_dict
    return None

def insert_extracted_story(story: dict) -> None:
    try:
        query = """
          INSERT INTO extracted_stories (
            story_id, cluster_id, headline_summary, key_facts, entities, event_type,
            quoted_statements, field_confidences, validation_score, hold_for_review
          ) VALUES (
            %(story_id)s, %(cluster_id)s, %(headline_summary)s, %(key_facts)s, %(entities)s, %(event_type)s,
            %(quoted_statements)s, %(field_confidences)s, %(validation_score)s, %(hold_for_review)s
          )
        """
        payload = {**story}
        payload["key_facts"] = json.dumps(story.get("key_facts", []))
        payload["entities"] = json.dumps(story.get("entities", {}))
        payload["quoted_statements"] = json.dumps(story.get("quoted_statements", []))
        payload["field_confidences"] = json.dumps(story.get("field_confidences", {}))
        payload["hold_for_review"] = int(bool(story.get("hold_for_review")))
        for key in ["headline_summary", "event_type"]:
            if key not in payload: payload[key] = None
        if "validation_score" not in payload: payload["validation_score"] = 0.0

        db.execute(query, payload)
    except Exception as error:
        raise handle_error(DBError("Failed to insert extracted story", {"story_id": story.get("story_id"), "error": str(error)}), logger, {"story_id": story.get("story_id")})

def update_extracted_story(story_id: str, fields: dict) -> None:
    query = """
      UPDATE extracted_stories
      SET field_confidences = COALESCE(%(field_confidences)s, field_confidences),
          validation_score = COALESCE(%(validation_score)s, validation_score),
          hold_for_review = COALESCE(%(hold_for_review)s, hold_for_review)
      WHERE story_id = %(story_id)s
    """
    payload = {
        "story_id": story_id,
        "field_confidences": json.dumps(fields["field_confidences"]) if "field_confidences" in fields else None,
        "validation_score": fields.get("validation_score"),
        "hold_for_review": int(bool(fields["hold_for_review"])) if "hold_for_review" in fields else None,
    }
    db.execute(query, payload)

def get_extracted_stories_by_run(run_id: str) -> list[dict]:
    query = """
      SELECT es.*, sc.run_id, sc.canonical_topic, sc.source_count, sc.item_ids
      FROM extracted_stories es
      INNER JOIN story_clusters sc ON sc.cluster_id = es.cluster_id
      WHERE sc.run_id = %s
      ORDER BY es.created_at ASC
    """
    rows = [dict(row) for row in db.execute(query, (run_id,)).fetchall()]
    for row in rows:
        row["key_facts"] = json.loads(row["key_facts"]) if row.get("key_facts") and isinstance(row["key_facts"], str) else (row.get("key_facts") or [])
        row["entities"] = json.loads(row["entities"]) if row.get("entities") and isinstance(row["entities"], str) else (row.get("entities") or {})
        row["quoted_statements"] = json.loads(row["quoted_statements"]) if row.get("quoted_statements") and isinstance(row["quoted_statements"], str) else (row.get("quoted_statements") or [])
        row["field_confidences"] = json.loads(row["field_confidences"]) if row.get("field_confidences") and isinstance(row["field_confidences"], str) else (row.get("field_confidences") or {})
        row["item_ids"] = json.loads(row["item_ids"]) if row.get("item_ids") and isinstance(row["item_ids"], str) else (row.get("item_ids") or [])
    return rows
