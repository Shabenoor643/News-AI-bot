# FILE: src/utils/parse_gemini_json.py | PURPOSE: Safe Gemini JSON parsing utility
import json
import re
from typing import Any
from src.utils.error_handler import GeminiParseError
from src.utils.logger import create_logger

try:
    import json5
    HAS_JSON5 = True
except ImportError:
    HAS_JSON5 = False

logger = create_logger("parse_gemini_json")

def parse_gemini_json(response_text: str, context: str) -> Any:
    raw_text = str(response_text or "").strip()
    
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", raw_text).strip().rstrip("`").strip()
    
    # Try strict JSON first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try json5 for permissive parsing (trailing commas, comments)
    if HAS_JSON5:
        try:
            return json5.loads(text)
        except Exception:
            pass
    
    # Last resort: extract first {...} block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
            
    # Try matching an array if it's not an object
    match_array = re.search(r'\[.*\]', text, re.DOTALL)
    if match_array:
        try:
            return json.loads(match_array.group())
        except json.JSONDecodeError:
            pass
    
    logger.error(f"Failed to parse Gemini JSON", extra={
        "context": context,
        "raw_text": raw_text[:300]
    })
    
    print(f"DEBUG RAW TEXT FOR {context}:\n{raw_text[:1000]}")
    raise GeminiParseError(f"Failed to parse Gemini JSON for {context}", {
        "context": context,
        "raw_text": raw_text[:300]
    })
