# FILE: src/utils/fingerprint.py | PURPOSE: Topic fingerprint + Jaccard similarity
import re
from typing import Set

STOP_WORDS = {
    "a", "an", "the", "is", "in", "on", "at", "to", "for", "of", "and", "or",
    "but", "with", "from", "by", "as", "that", "this", "was", "are", "be",
    "has", "have", "had", "its", "it", "will", "new", "also", "after", "before",
}

def generate_fingerprint(title: str) -> Set[str]:
    sanitized = re.sub(r'[^a-z0-9\s]', ' ', str(title or "").lower())
    tokens = [t for t in re.split(r'\s+', sanitized) if t and len(t) >= 3 and t not in STOP_WORDS]
    
    selected = []
    for token in tokens:
        if token not in selected:
            selected.append(token)
        if len(selected) >= 8:
            break
            
    return set(sorted(selected))

def jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    intersection = {x for x in set_a if x in set_b}
    union = set_a.union(set_b)
    return len(intersection) / len(union) if union else 0.0
