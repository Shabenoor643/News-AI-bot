# FILE: src/agents/filter_agent.py | PURPOSE: Stage 3 — keyword-based relevance scoring
from src.config.config import CONFIG
from src.db.queries.raw_items import update_raw_item_score
from src.utils.error_handler import handle_error
from src.utils.logger import create_logger

logger = create_logger("filter_agent")

def score_raw_item(item: dict) -> float:
    title = str(item.get("title", "")).lower()
    snippet = str(item.get("snippet", "")).lower()
    keywords = CONFIG.Keywords.motorcycle
    penalties = CONFIG.Keywords.penalties

    title_match = any(keyword in title for keyword in keywords)
    snippet_match = any(keyword in snippet for keyword in keywords)
    penalty_hit = any(keyword in title or keyword in snippet for keyword in penalties)

    score = 0.0
    if title_match:
        score += 0.4
    if snippet_match:
        score += 0.3
    if title_match and snippet_match:
        score += 0.2
    if penalty_hit:
        score -= 0.3
    if item.get("language", "en") != "en":
        score -= 0.2

    return max(0.0, min(1.0, round(score, 2)))

async def run_filter_agent(raw_items: list[dict]) -> list[dict]:
    try:
        filtered = []

        for item in raw_items:
            score = score_raw_item(item)
            status = "filtered_in" if score >= CONFIG.Pipeline.relevance_threshold else "filtered_out"
            update_raw_item_score(item["item_id"], score, status)
            item["relevance_score"] = score
            item["status"] = status

            if score >= CONFIG.Pipeline.relevance_threshold:
                filtered.append(item)

        logger.info("Filter complete", extra={
            "total_items": len(raw_items),
            "passed": len(filtered),
            "threshold": CONFIG.Pipeline.relevance_threshold,
        })

        return filtered
    except Exception as error:
        raise handle_error(error, logger, {"agent": "filter_agent"})
