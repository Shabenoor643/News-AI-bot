import os
import hashlib
import json
import re
from dataclasses import dataclass
from google import genai
from google.genai import types

from src.config.config import CONFIG
from src.utils.logger import create_logger
from src.utils.observability import estimate_image_cost_inr, estimate_text_cost_inr
from src.utils.sleep import sleep
from src.utils.parse_gemini_json import parse_gemini_json
from src.utils.error_handler import GeminiInputError

logger = create_logger("llm_service")


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_inr: float = 0.0
    cache_hit: bool = False
    image_count: int = 0


def _get_usage_value(source, *names: str) -> int:
    if source is None:
        return 0
    for name in names:
        if isinstance(source, dict) and source.get(name) is not None:
            return int(source.get(name) or 0)
        if hasattr(source, name):
            value = getattr(source, name)
            if value is not None:
                return int(value or 0)
    return 0

class LLMService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMService, cls).__new__(cls)
            cls._instance._init_service()
        return cls._instance

    def _init_service(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        self.client = genai.Client(api_key=api_key)
        self.cache = {}

    def compress_prompt(self, text: str) -> str:
        # Strip excessive whitespace and repetitive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    def _get_cache_key(self, model: str, contents: any, config: types.GenerateContentConfig) -> str:
        # Create a hashable string from inputs
        data_to_hash = {
            "model": model,
            "contents": str(contents),
            "config": str(config) if config else ""
        }
        json_str = json.dumps(data_to_hash, sort_keys=True)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    def _extract_text_usage(self, response) -> LLMUsage:
        usage_metadata = getattr(response, "usage_metadata", None)
        prompt_tokens = _get_usage_value(
            usage_metadata,
            "prompt_token_count",
            "input_token_count",
            "input_tokens",
        )
        completion_tokens = _get_usage_value(
            usage_metadata,
            "candidates_token_count",
            "output_token_count",
            "output_tokens",
        )
        total_tokens = _get_usage_value(
            usage_metadata,
            "total_token_count",
            "total_tokens",
        )
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens
        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_inr=estimate_text_cost_inr(prompt_tokens, completion_tokens),
        )

    async def generate_content(self, model: str, contents: any, config: types.GenerateContentConfig = None, context_label: str = "llm", parse_json: bool = False):
        result, _ = await self.generate_content_with_usage(
            model=model,
            contents=contents,
            config=config,
            context_label=context_label,
            parse_json=parse_json,
        )
        return result

    async def generate_content_with_usage(self, model: str, contents: any, config: types.GenerateContentConfig = None, context_label: str = "llm", parse_json: bool = False):
        if isinstance(contents, str):
            contents = self.compress_prompt(contents)

        cache_key = self._get_cache_key(model, contents, config)
        if cache_key in self.cache:
            logger.info("LLM cache hit", extra={"context": context_label})
            return self.cache[cache_key], LLMUsage(cache_hit=True)

        for attempt in range(1, CONFIG.Gemini.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                
                result = response
                if parse_json:
                    result = parse_gemini_json(response.text, context_label)
                
                self.cache[cache_key] = result
                return result, self._extract_text_usage(response)
            except Exception as error:
                status = getattr(error, "code", 0)
                if status == 400:
                    logger.warning(f"Bad request (400) from Gemini for {context_label}. Not retrying.")
                    raise error
                if attempt >= CONFIG.Gemini.max_retries:
                    raise error
                
                delay = 60000 if status == 429 else (attempt * 5000 if status == 503 else attempt * 2000)
                logger.warning(f"LLM retrying for {context_label}", extra={"attempt": attempt, "status": status, "delay": delay})
                await sleep(delay)

    async def generate_images(self, prompt: str, config: types.GenerateImagesConfig):
        result, _ = await self.generate_images_with_usage(prompt, config)
        return result

    async def generate_images_with_usage(self, prompt: str, config: types.GenerateImagesConfig):
        prompt = self.compress_prompt(prompt)
        for attempt in range(1, CONFIG.Gemini.max_retries + 1):
            try:
                response = self.client.models.generate_images(
                    model=CONFIG.Gemini.image_model,
                    prompt=prompt,
                    config=config
                )
                generated_images = getattr(response, "generated_images", []) or []
                usage = LLMUsage(
                    image_count=len(generated_images),
                    cost_inr=estimate_image_cost_inr(len(generated_images)),
                )
                return response, usage
            except Exception as error:
                status = getattr(error, "code", 0)
                if status == 400:
                    raise error
                if attempt >= CONFIG.Gemini.max_retries:
                    raise error
                
                delay = 60000 if status == 429 else (attempt * 5000 if status == 503 else attempt * 2000)
                logger.warning("Imagen retrying", extra={"attempt": attempt, "status": status, "delay": delay})
                await sleep(delay)

llm_service = None
