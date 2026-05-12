# FILE: src/agents/grouping_agent.py | PURPOSE: Stage 4 — cluster stories by topic fingerprint
import uuid
from typing import Set
from dateutil import parser
from src.db.queries.story_clusters import insert_story_cluster
from src.utils.fingerprint import generate_fingerprint, jaccard_similarity
from src.utils.error_handler import handle_error
from src.utils.logger import create_logger

logger = create_logger("grouping_agent")

class UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, index: int) -> int:
        if self.parent[index] != index:
            self.parent[index] = self.find(self.parent[index])
        return self.parent[index]

    def union(self, a: int, b: int) -> None:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a != root_b:
            self.parent[root_b] = root_a

def _get_time(item: dict) -> float:
    if item.get("published_at"):
        try:
            return parser.parse(item["published_at"]).timestamp() * 1000
        except Exception:
            pass
    return float('inf')

def select_canonical_item(items: list[dict]) -> dict:
    sorted_items = sorted(
        items,
        key=lambda x: (_get_time(x), -(x.get("relevance_score", 0)))
    )
    return sorted_items[0]

def combine_fingerprints(fingerprints: list[Set[str]]) -> Set[str]:
    combined = set()
    for f in fingerprints:
        combined.update(f)
    return combined

def detect_story_type(cluster: dict) -> str:
    combined_text = cluster.get("canonical_topic", "").lower()
    for item in cluster.get("items", []):
        combined_text += " " + item.get("title", "").lower() + " " + item.get("snippet", "").lower()
    
    if any(word in combined_text for word in ["launch", "launched", "unveil", "unveiled", "introduced"]):
        return "launch"
    if any(word in combined_text for word in ["price drop", "price reduced", "price cut", "cheaper"]):
        return "price_drop"
    if any(word in combined_text for word in ["price hike", "price increased", "more expensive"]):
        return "price_hike"
    if any(word in combined_text for word in ["discontinued", "axed", "delisted", "pulled the plug"]):
        return "discontinued"
    if any(word in combined_text for word in ["review", "ridden", "road test", "first ride"]):
        return "review"
    if any(word in combined_text for word in ["update", "facelift", "new colors", "new colours", "upgraded"]):
        return "update"
    return "unknown"

async def run_grouping_agent(filtered_items: list[dict], run_id: str) -> list[dict]:
    try:
        if not filtered_items:
            return []

        fingerprints = [generate_fingerprint(item.get("title", "")) for item in filtered_items]
        uf = UnionFind(len(filtered_items))

        for index in range(len(filtered_items)):
            for compare_index in range(index + 1, len(filtered_items)):
                if jaccard_similarity(fingerprints[index], fingerprints[compare_index]) >= 0.5:
                    uf.union(index, compare_index)

        groups = {}
        for index, item in enumerate(filtered_items):
            root = uf.find(index)
            if root not in groups:
                groups[root] = []
            groups[root].append({"item": item, "fingerprint": fingerprints[index]})

        merged_clusters = []
        for group in groups.values():
            items = [entry["item"] for entry in group]
            cluster_fingerprint = combine_fingerprints([entry["fingerprint"] for entry in group])
            
            target_cluster = next((c for c in merged_clusters if jaccard_similarity(c["cluster_fingerprint"], cluster_fingerprint) >= 0.7), None)
            if not target_cluster:
                target_cluster = {"items": [], "cluster_fingerprint": set()}
                merged_clusters.append(target_cluster)
                
            target_cluster["items"].extend(items)
            target_cluster["cluster_fingerprint"] = combine_fingerprints([target_cluster["cluster_fingerprint"], cluster_fingerprint])

        story_clusters = []
        for group in merged_clusters:
            canonical_item = select_canonical_item(group["items"])
            cluster = {
                "cluster_id": str(uuid.uuid4()),
                "run_id": run_id,
                "canonical_topic": canonical_item.get("title", ""),
                "source_count": len(group["items"]),
                "low_confidence": len(group["items"]) == 1,
                "item_ids": [item["item_id"] for item in group["items"]],
                "items": group["items"],
                "canonical_item": canonical_item,
                "cluster_fingerprint": group["cluster_fingerprint"],
            }
            cluster["story_type"] = detect_story_type(cluster)
            story_clusters.append(cluster)

        for cluster in story_clusters:
            # We don't save cluster_fingerprint and canonical_item to db, only simple dict
            insert_story_cluster(cluster)

        logger.info("Grouping complete", extra={
            "run_id": run_id,
            "input_items": len(filtered_items),
            "clusters": len(story_clusters),
        })

        return story_clusters
    except Exception as error:
        raise handle_error(error, logger, {"agent": "grouping_agent", "run_id": run_id})
