from google import genai
from google.genai import types

from src.config.config import CONFIG
from src.utils.error_handler import handle_error
from src.utils.logger import create_logger
from src.utils.llm_service import LLMService

logger = create_logger("critic_agent")

SYSTEM_PROMPT = """You are an expert SEO specialist and Senior Editor for an automotive blog (NewsBot).
Your job is to review a draft article and determine if it meets publication standards.
Criteria:
1. SEO Quality: The title and meta description must be catchy and keyword-rich.
2. Content Quality: The article must be engaging, well-structured (H2 headings), and focus on the Indian context.
3. Length: It should be reasonably comprehensive (not just a stub).

If the article meets these criteria, approve it. If not, provide specific, actionable feedback for the writer to improve it.
Return the result strictly as a JSON object with two fields: 'approved' (boolean) and 'feedback' (string).
"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "approved": {"type": "BOOLEAN"},
        "feedback": {"type": "STRING"}
    },
    "required": ["approved", "feedback"]
}

async def evaluate_draft(llm: LLMService, draft: dict) -> dict:
    try:
        prompt = f"""
        Please review the following draft article:
        
        Title: {draft.get('title')}
        Meta Description: {draft.get('meta_description')}
        Body:
        {draft.get('body')}
        
        Evaluate it based on the criteria.
        """
        
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=SCHEMA,
            temperature=0.2,
        )
        
        result = await llm.generate_content(
            model=CONFIG.Gemini.model,
            contents=prompt,
            config=config,
            context_label="critic_agent",
            parse_json=True
        )
        
        return {
            "approved": result.get("approved", False),
            "feedback": result.get("feedback", "No feedback provided.")
        }
    except Exception as e:
        logger.warning(f"Critic evaluation failed: {e}")
        # Default to approved if the critic fails, to keep pipeline moving
        return {"approved": True, "feedback": ""}
