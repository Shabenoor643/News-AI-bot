import re


BIKE_BRANDS = [
    "Royal Enfield",
    "Harley-Davidson",
    "Hero MotoCorp",
    "Hero",
    "Honda",
    "Bajaj",
    "TVS",
    "Yamaha",
    "Suzuki",
    "KTM",
    "Kawasaki",
    "Triumph",
    "Ducati",
    "BMW Motorrad",
    "BMW",
    "Ather",
    "Ola Electric",
    "Ola",
    "Simple Energy",
    "Revolt",
    "Ultraviolette",
]


def extract_bike_name(draft: dict) -> str:
    title = str(draft.get("title") or "").strip()
    body = str(draft.get("body") or "")[:400]
    search_space = f"{title}\n{body}"
    brand_pattern = "|".join(sorted((re.escape(name) for name in BIKE_BRANDS), key=len, reverse=True))
    match = re.search(
        rf"({brand_pattern})\s+[A-Z0-9][A-Za-z0-9-]+(?:\s+[A-Z0-9][A-Za-z0-9-]+){{0,3}}",
        search_space,
    )
    if match:
        return match.group(0).strip(" .,")

    fallback = re.split(r"[:|,-]", title)[0].strip()
    return " ".join(fallback.split()[:5]).strip() or "motorcycle"
