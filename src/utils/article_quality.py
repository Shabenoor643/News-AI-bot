import re

from src.config.config import CONFIG


REQUIRED_HEADINGS = [
    "## What's new",
    "## Design / Features",
    "## Engine / Performance",
    "## Price & Positioning",
    "## Should You Care?",
]

BANNED_PATTERNS = [
    r"#",
    r"\bfaq\b",
    r"\btable of contents\b",
    r"\bin conclusion\b",
    r"\bin this article\b",
]


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def sanitize_article_markdown(article: str) -> str:
    text = str(article or "").replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    heading_map = {
        "what's new": "## What's new",
        "what is new": "## What's new",
        "design / features": "## Design / Features",
        "design and features": "## Design / Features",
        "features": "## Design / Features",
        "engine / performance": "## Engine / Performance",
        "engine and performance": "## Engine / Performance",
        "performance": "## Engine / Performance",
        "price & positioning": "## Price & Positioning",
        "price and positioning": "## Price & Positioning",
        "price": "## Price & Positioning",
        "should you care?": "## Should You Care?",
        "should you care": "## Should You Care?",
    }

    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            cleaned_lines.append("")
            continue
        if line.startswith("# "):
            continue
        if line.startswith("### "):
            normalized = line[4:].strip().lower()
            cleaned_lines.append(heading_map.get(normalized, line))
            continue
        if line.startswith("## "):
            normalized = line[3:].strip().lower()
            cleaned_lines.append(heading_map.get(normalized, line))
            continue
        cleaned_lines.append(line)

    sanitized = "\n".join(cleaned_lines)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()
    return sanitized


def assess_article_quality(article: str) -> dict:
    text = sanitize_article_markdown(article)
    lowered = text.lower()
    word_count = count_words(text)
    heading_hits = sum(1 for heading in REQUIRED_HEADINGS if heading.lower() in lowered)
    banned_hits = [
        pattern for pattern in BANNED_PATTERNS
        if re.search(pattern, lowered)
    ]
    buyer_intent_present = any(
        phrase in lowered
        for phrase in [
            "value for money",
            "best for",
            "not ideal for",
            "buyers",
            "daily commuters",
            "beginners",
        ]
    )
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    hook_ok = len(lines) >= 2 and not lines[0].startswith("##") and not lines[1].startswith("##")

    score = 0
    score += 40 if CONFIG.Pipeline.article_min_words <= word_count <= CONFIG.Pipeline.article_max_words else 10
    score += heading_hits * 8
    score += 15 if buyer_intent_present else 0
    score += 10 if hook_ok else 0
    score += 10 if not banned_hits else 0
    score = min(score, 100)

    return {
        "score": score,
        "word_count": word_count,
        "heading_hits": heading_hits,
        "buyer_intent_present": buyer_intent_present,
        "banned_hits": banned_hits,
        "eligible": (
            CONFIG.Pipeline.article_min_words <= word_count <= CONFIG.Pipeline.article_max_words
            and heading_hits == len(REQUIRED_HEADINGS)
            and buyer_intent_present
            and not banned_hits
            and hook_ok
        ),
        "article": text,
    }
