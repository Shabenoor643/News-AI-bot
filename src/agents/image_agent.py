import os
from src.utils.llm_service import LLMService
import io
import asyncio
import json
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

from src.config.config import CONFIG
from src.db.queries.draft_articles import update_draft_article
from src.utils.logger import create_logger
from src.utils.parse_gemini_json import parse_gemini_json
from src.utils.gemini_schemas import ImageValidationResult

logger = create_logger("image_agent")

IMAGE_VALIDATOR_PROMPT = """Analyze this generated motorcycle image. Return JSON only:
{
  "humans_present": boolean,
  "full_vehicle_visible": boolean,
  "vehicle_cropped": boolean,
  "background_clean": boolean,
  "overall_pass": boolean
}
Set overall_pass true ONLY IF: humans_present=false AND full_vehicle_visible=true AND vehicle_cropped=false."""

async def validate_generated_image(llm: LLMService, image_bytes: bytes) -> dict | None:
    try:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type='image/png')
        response = await llm.generate_content(
            model='gemini-2.5-flash',
            contents=[image_part, "Analyze this generated image."],
            config=types.GenerateContentConfig(
                system_instruction=IMAGE_VALIDATOR_PROMPT,
                temperature=0.1
            ),
            context_label="image_validator",
            parse_json=True
        )
        validated = ImageValidationResult(**response)
        return validated.model_dump()
    except Exception as e:
        logger.warning(f"Image validation failed: {e}")
        return None

def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        line_w = draw.textlength(" ".join(current_line), font=font)
        if line_w > max_width:
            if len(current_line) > 1:
                current_line.pop()
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(" ".join(current_line))
                current_line = []
    if current_line:
        lines.append(" ".join(current_line))
    return lines[:3]


# Active search-and-generate runtime path.
import httpx
from PIL import ImageOps

from src.prompts.image_prompts import build_image_search_queries
from src.utils.bike_name import extract_bike_name
from src.utils.observability import AgentTrace

GEMINI_IMAGE_SEARCH_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "subject_name": {"type": "STRING"},
        "visual_summary": {"type": "STRING"},
        "visual_cues": {"type": "ARRAY", "items": {"type": "STRING"}},
        "camera_angle": {"type": "STRING"},
        "background_hint": {"type": "STRING"},
        "color_hint": {"type": "STRING"},
        "negative_cues": {"type": "ARRAY", "items": {"type": "STRING"}},
        "source_titles": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": [
        "subject_name",
        "visual_summary",
        "visual_cues",
        "camera_angle",
        "background_hint",
        "color_hint",
        "negative_cues",
        "source_titles",
    ],
}

GEMINI_IMAGE_SEARCH_PROMPT = """You research authoritative visual references for motorcycle and scooter imagery.
Use Google Search grounding to understand how the vehicle looks in official launches, press kits, and reputable automotive coverage.
Return only JSON matching the schema.

Rules:
- Prioritize manufacturer pages, launch coverage, and trusted motorcycle outlets.
- Focus on details that help image generation: silhouette, tank shape, fairing style, wheel type, seat shape, lighting signature, and likely camera angle.
- Prefer side-profile or 3/4-profile reference material.
- Do not invent details. If something is unclear, use "unknown" or an empty array.
- Exclude action shots, rider shots, racing scenes, crowds, watermarks, and heavy crops from the recommended look."""

DEFAULT_NEGATIVE_CUES = [
    "humans",
    "riders",
    "helmets",
    "logos",
    "text overlays",
    "watermarks",
    "crowds",
    "multiple vehicles",
    "cropped vehicle",
    "motion blur",
]


def _compact_text_v3(value: object, limit: int = 900) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:limit]


def _normalize_text_list_v3(values: object, limit: int = 8) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized = []
    seen = set()
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _extract_grounding_sources_v3(response) -> list[dict]:
    sources = []
    seen = set()
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return sources

    grounding_metadata = getattr(candidates[0], "grounding_metadata", None)
    grounding_chunks = getattr(grounding_metadata, "grounding_chunks", None) or []
    for chunk in grounding_chunks:
        web = getattr(chunk, "web", None)
        url = str(getattr(web, "uri", "") or "").strip()
        title = str(getattr(web, "title", "") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        sources.append({"title": title, "url": url})
        if len(sources) >= CONFIG.ImageSearch.max_candidates:
            break
    return sources


def _has_search_context_v3(context: dict | None) -> bool:
    if not context:
        return False
    if _compact_text_v3(context.get("visual_summary")):
        return True
    return bool(_normalize_text_list_v3(context.get("visual_cues")))


async def gemini_image_search(llm: LLMService, query: str, bike_name: str, draft: dict) -> dict | None:
    prompt = "\n".join(
        [
            f"Search query: {query}",
            f"Vehicle: {bike_name}",
            f"Article title: {_compact_text_v3(draft.get('title'))}",
            f"Article excerpt: {_compact_text_v3(draft.get('body'))}",
            "Return grounded visual guidance for generating a clean editorial hero image.",
        ]
    )

    try:
        response = await llm.generate_content(
            model=CONFIG.Gemini.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=GEMINI_IMAGE_SEARCH_PROMPT,
                tools=[{"google_search": {}}],
                response_mime_type="application/json",
                response_schema=GEMINI_IMAGE_SEARCH_SCHEMA,
                temperature=0.1,
            ),
            context_label="gemini_image_search",
            parse_json=False,
        )
        parsed = parse_gemini_json(response.text, "gemini_image_search")
        context = {
            "strategy": "gemini_google_search",
            "query": query,
            "subject_name": _compact_text_v3(parsed.get("subject_name")) or bike_name,
            "visual_summary": _compact_text_v3(parsed.get("visual_summary")),
            "visual_cues": _normalize_text_list_v3(parsed.get("visual_cues")),
            "camera_angle": _compact_text_v3(parsed.get("camera_angle")) or "3/4 side profile",
            "background_hint": _compact_text_v3(parsed.get("background_hint")) or "clean premium studio background",
            "color_hint": _compact_text_v3(parsed.get("color_hint")) or "production color",
            "negative_cues": _normalize_text_list_v3(parsed.get("negative_cues")),
            "source_titles": _normalize_text_list_v3(parsed.get("source_titles")),
            "source_urls": [source["url"] for source in _extract_grounding_sources_v3(response)],
        }
        if not _has_search_context_v3(context):
            return None
        return context
    except Exception as error:
        logger.warning("Gemini image search failed", extra={"query": query, "error": str(error)})
        return None


async def search_images_serpapi(client: httpx.AsyncClient, query: str, bike_name: str) -> dict | None:
    if not CONFIG.ImageSearch.serpapi_key:
        return None

    try:
        response = await client.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google_images",
                "q": query,
                "api_key": CONFIG.ImageSearch.serpapi_key,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as error:
        logger.warning("SerpAPI image search failed", extra={"query": query, "error": str(error)})
        return None

    results = payload.get("images_results", [])[: CONFIG.ImageSearch.max_candidates]
    if not results:
        return None

    source_titles = []
    source_urls = []
    visual_cues = []

    for item in results:
        title = _compact_text_v3(item.get("title"), limit=140)
        source_title = _compact_text_v3(item.get("source"), limit=80)
        source_url = _compact_text_v3(item.get("link") or item.get("original") or item.get("thumbnail"), limit=400)
        if title:
            source_titles.append(title)
            visual_cues.append(title)
        if source_title:
            visual_cues.append(source_title)
        if source_url:
            source_urls.append(source_url)

    context = {
        "strategy": "serpapi_fallback",
        "query": query,
        "subject_name": bike_name,
        "visual_summary": f"Fallback search results for {bike_name} describe official or editorial motorcycle imagery.",
        "visual_cues": _normalize_text_list_v3(visual_cues),
        "camera_angle": "side or 3/4 side profile",
        "background_hint": "clean editorial or studio-style background",
        "color_hint": "production color",
        "negative_cues": ["rider shots", "action shots", "cropped bike", "watermarks"],
        "source_titles": _normalize_text_list_v3(source_titles),
        "source_urls": _normalize_text_list_v3(source_urls, limit=CONFIG.ImageSearch.max_candidates),
    }
    if not _has_search_context_v3(context):
        return None
    return context


async def _discover_image_context_v3(
    llm: LLMService,
    client: httpx.AsyncClient,
    bike_name: str,
    draft: dict,
) -> dict | None:
    queries = build_image_search_queries(bike_name)

    if CONFIG.ImageSearch.use_gemini_search:
        for query in queries:
            context = await gemini_image_search(llm, query, bike_name, draft)
            if context:
                return context

    if CONFIG.ImageSearch.serpapi_key:
        for query in queries:
            context = await search_images_serpapi(client, query, bike_name)
            if context:
                return context

    return None


def _build_generation_prompt_v3(bike_name: str, draft: dict, context: dict) -> str:
    cues = ", ".join(context.get("visual_cues", [])[:6]) or "clean production design"
    source_titles = ", ".join(context.get("source_titles", [])[:4])
    negative_cues = _normalize_text_list_v3(context.get("negative_cues")) or []
    avoid_text = ", ".join(_normalize_text_list_v3(DEFAULT_NEGATIVE_CUES + negative_cues, limit=12))
    visual_summary = _compact_text_v3(context.get("visual_summary")) or f"authoritative references for {bike_name}"
    camera_angle = _compact_text_v3(context.get("camera_angle")) or "3/4 side profile"
    background_hint = _compact_text_v3(context.get("background_hint")) or "clean studio backdrop"
    color_hint = _compact_text_v3(context.get("color_hint")) or "production color"

    prompt_parts = [
        f"Create a realistic editorial hero image of the {bike_name}.",
        f"Grounded reference summary: {visual_summary}.",
        f"Reference cues: {cues}.",
        f"Camera angle: {camera_angle}.",
        f"Color guidance: {color_hint}.",
        f"Background: {background_hint}.",
        f"Story context: {_compact_text_v3(draft.get('title'))}.",
        "Composition: a single motorcycle or scooter only, fully visible in frame, centered for a 16:9 hero image.",
        "Style: premium commercial product photography with realistic materials and sharp details.",
        f"Avoid: {avoid_text}.",
        "Do not add text, logos, riders, people, extra vehicles, or watermarks.",
    ]
    if source_titles:
        prompt_parts.append(f"Reference source titles: {source_titles}.")
    return " ".join(prompt_parts)


def _build_retry_prompt_v3(prompt: str, validation: dict | None) -> str:
    if not validation:
        return prompt + " Keep the vehicle fully visible and remove any people."

    corrections = []
    if validation.get("humans_present"):
        corrections.append("Remove all people, riders, and helmets.")
    if validation.get("vehicle_cropped"):
        corrections.append("Keep the full vehicle inside the frame with clear spacing.")
    if not validation.get("background_clean", True):
        corrections.append("Use a clean premium studio background with no clutter.")

    if not corrections:
        corrections.append("Maintain a clean studio product shot with the full bike visible.")
    return prompt + " " + " ".join(corrections)


def _load_font_v3(size: int):
    font_path = "src/assets/fonts/Roboto-Black.ttf"
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def _finalize_generated_image_v3(image_bytes: bytes, bike_name: str) -> bytes:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    canvas = ImageOps.fit(image, (1280, 720), method=Image.Resampling.LANCZOS)

    if CONFIG.ImageSearch.overlay_text:
        draw = ImageDraw.Draw(canvas)
        font = _load_font_v3(40)
        label = bike_name[:42]
        text_width = int(draw.textlength(label, font=font))
        draw.rectangle((44, 42, 84 + text_width, 108), fill=(14, 52, 40, 180))
        draw.text((64, 54), label, font=font, fill=(255, 255, 255, 255))

    buffer = io.BytesIO()
    for quality in range(88, 51, -4):
        buffer.seek(0)
        buffer.truncate(0)
        canvas.convert("RGB").save(buffer, format="WEBP", quality=quality, method=6)
        if buffer.tell() <= CONFIG.ImageSearch.max_output_bytes:
            return buffer.getvalue()
    return buffer.getvalue()


def _write_image_bytes_v3(path: str, image_bytes: bytes) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as image_file:
        image_file.write(image_bytes)
    return path


def _create_fallback_placeholder_v3(path: str, bike_name: str, draft: dict) -> str:
    background = Image.new("RGBA", (1280, 720), (235, 247, 241, 255))
    draw = ImageDraw.Draw(background)
    title_font = _load_font_v3(56)
    body_font = _load_font_v3(28)

    draw.rectangle((0, 0, 1280, 720), fill=(235, 247, 241, 255))
    draw.rectangle((72, 72, 1208, 648), outline=(36, 91, 72, 255), width=4)

    lines = wrap_text(bike_name, title_font, 980, draw)
    y_offset = 180
    for line in lines:
        draw.text((96, y_offset), line, font=title_font, fill=(24, 79, 58, 255))
        y_offset += 74

    subtitle = _compact_text_v3(draft.get("title"), limit=120) or "Motorcycle update"
    draw.text((96, y_offset + 20), subtitle, font=body_font, fill=(48, 92, 78, 255))
    draw.text(
        (96, y_offset + 86),
        "Generated placeholder: grounded search context unavailable.",
        font=body_font,
        fill=(67, 108, 94, 255),
    )

    buffer = io.BytesIO()
    background.convert("RGB").save(buffer, format="WEBP", quality=84, method=6)
    return _write_image_bytes_v3(path, buffer.getvalue())


def _build_alt_text_v3(bike_name: str, draft: dict) -> str:
    category = _compact_text_v3(draft.get("category"), limit=40) or "motorcycle update"
    return f"{bike_name} - {category} hero image"[:120]


async def _generate_best_image_v3(llm: LLMService, bike_name: str, draft: dict, context: dict) -> tuple[bytes | None, dict | None, str]:
    prompt = _build_generation_prompt_v3(bike_name, draft, context)
    last_validation = None
    best_bytes = None

    for _ in range(3):
        try:
            result = await llm.generate_images(
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/png",
                    aspect_ratio="16:9",
                ),
            )
            generated = getattr(result, "generated_images", None) or []
            if not generated:
                continue

            candidate_bytes = generated[0].image.image_bytes
            best_bytes = candidate_bytes
            last_validation = await validate_generated_image(llm, candidate_bytes)
            if last_validation and last_validation.get("overall_pass"):
                finalized = await asyncio.to_thread(_finalize_generated_image_v3, candidate_bytes, bike_name)
                return finalized, last_validation, "ok"

            prompt = _build_retry_prompt_v3(prompt, last_validation)
        except Exception as error:
            logger.warning("Internal image generation failed", extra={"bike_name": bike_name, "error": str(error)})

    if best_bytes:
        finalized = await asyncio.to_thread(_finalize_generated_image_v3, best_bytes, bike_name)
        return finalized, last_validation, "needs_review"
    return None, last_validation, "generation_failed"


async def run_image_agent(drafts: list[dict], job_id: str) -> list[dict]:
    results = []
    llm = LLMService()
    timeout = httpx.Timeout(CONFIG.ImageSearch.timeout_seconds)

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0 (NewsBotBot/1.0)"},
    ) as client:
        for draft in drafts:
            draft_id = draft.get("article_id")
            trace = AgentTrace(
                agent_name="image_agent",
                action="generate_article_image",
                input_summary=str(draft.get("title") or draft_id),
                extra_params={"run_id": job_id, "article_id": draft_id},
            )
            try:
                hero_path = os.path.join(CONFIG.Paths.images_dir, f"{draft.get('slug')}-hero.webp")
                if draft.get("image_status") == "ready" and draft.get("image_url") and os.path.exists(str(draft.get("image_url"))):
                    trace.status = "skipped"
                    trace.output_summary = str(draft.get("image_url"))
                    results.append({"article_id": draft_id, "image_path": draft.get("image_url"), "status": "ready"})
                    continue

                bike_name = extract_bike_name(draft)
                context = await _discover_image_context_v3(llm, client, bike_name, draft)

                if context:
                    image_bytes, validation, quality_flag = await _generate_best_image_v3(llm, bike_name, draft, context)
                else:
                    image_bytes, validation, quality_flag = None, None, "fallback_placeholder"

                if image_bytes:
                    final_path = await asyncio.to_thread(_write_image_bytes_v3, hero_path, image_bytes)
                    image_source = f"generated:{context.get('strategy')}" if context else "generated"
                    status = "ready"
                else:
                    final_path = await asyncio.to_thread(_create_fallback_placeholder_v3, hero_path, bike_name, draft)
                    image_source = "placeholder"
                    status = "fallback"

                audit_payload = {
                    "bike_name": bike_name,
                    "search_strategy": context.get("strategy") if context else "none",
                    "search_query": context.get("query") if context else None,
                    "search_summary": context.get("visual_summary") if context else None,
                    "source_titles": context.get("source_titles") if context else [],
                    "source_urls": context.get("source_urls") if context else [],
                    "validator_result": validation,
                    "quality_flag": quality_flag,
                }

                update_draft_article(
                    draft_id,
                    {
                        "image_prompt": _build_generation_prompt_v3(bike_name, draft, context) if context else "placeholder",
                        "image_url": final_path,
                        "image_source": image_source,
                        "alt_text": _build_alt_text_v3(bike_name, draft),
                        "image_status": "ready",
                        "image_quality_flag": quality_flag,
                        "pipeline_stage": "image_done",
                        "vision_analysis_json": json.dumps(audit_payload),
                    },
                )
                trace.output_summary = f"{status}:{final_path}"
                results.append({"article_id": draft_id, "image_path": final_path, "status": status})
            except Exception as error:
                trace.fail(error)
                fallback_path = os.path.join(CONFIG.Paths.images_dir, f"{draft.get('slug')}-hero.webp")
                try:
                    bike_name = extract_bike_name(draft)
                    final_path = await asyncio.to_thread(_create_fallback_placeholder_v3, fallback_path, bike_name, draft)
                    update_draft_article(
                        draft_id,
                        {
                            "image_prompt": "placeholder",
                            "image_url": final_path,
                            "image_source": "placeholder",
                            "alt_text": _build_alt_text_v3(bike_name, draft),
                            "image_status": "ready",
                            "image_quality_flag": "fallback_placeholder",
                            "pipeline_stage": "image_done",
                            "vision_analysis_json": json.dumps({"bike_name": bike_name, "reason": str(error)}),
                        },
                    )
                    results.append({"article_id": draft_id, "image_path": final_path, "status": "fallback"})
                except Exception:
                    logger.error("Image fallback failed", extra={"article_id": draft_id, "error": str(error)}, exc_info=True)
                    results.append({"article_id": draft_id, "image_path": None, "status": "failed"})
                logger.error("Image agent error", extra={"article_id": draft_id, "error": str(error)}, exc_info=True)
            finally:
                await trace.flush()
    return results
