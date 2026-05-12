IMAGE_SEARCH_QUERY_TEMPLATE = "{bike_name} official image side view"
IMAGE_SEARCH_FALLBACK_TEMPLATE = "{bike_name} official motorcycle profile image"
IMAGE_OVERLAY_TEMPLATE = "{bike_name}"


def build_image_search_queries(bike_name: str) -> list[str]:
    normalized_name = " ".join(str(bike_name or "motorcycle").split()).strip() or "motorcycle"
    return [
        IMAGE_SEARCH_QUERY_TEMPLATE.format(bike_name=normalized_name),
        IMAGE_SEARCH_FALLBACK_TEMPLATE.format(bike_name=normalized_name),
    ]
