# FILE: src/config/config.py | PURPOSE: Centralized config constants
import os
from datetime import date


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None

class Config:
    class Gemini:
        model = "gemini-2.5-flash-lite"
        image_model = "imagen-3.0-generate-002"
        temperature = 0.7
        max_output_tokens = 2048
        rate_limit_delay_ms = 2000
        image_rate_limit_delay_ms = 6000
        max_retries = max(1, int(os.getenv("MAX_RETRIES", "2")))

    class Pipeline:
        crawl_interval_hours = int(os.getenv("CRAWL_INTERVAL_HOURS", "6"))
        lookback_window_hours = 24
        lookback_window_days = int(os.getenv("LOOKBACK_WINDOW_DAYS", "5"))
        crawl_start_date = _parse_iso_date(os.getenv("CRAWL_START_DATE"))
        crawl_end_date = _parse_iso_date(os.getenv("CRAWL_END_DATE"))
        relevance_threshold = float(os.getenv("RELEVANCE_THRESHOLD", "0.6"))
        min_sources_for_validation = 2
        validation_score_threshold = 0.4
        article_min_words = 800
        article_max_words = 1200
        max_approval_emails = int(os.getenv("MAX_APPROVAL_EMAILS", "5"))
        approval_timeout_hours = 48
        max_edit_cycles = 2

    class Keywords:
        motorcycle = [
            "motorcycle", "bike", "two-wheeler", "scooter", "moped",
            "bajaj", "hero", "tvs", "royal enfield", "honda", "yamaha", "suzuki",
            "kawasaki", "ktm", "triumph", "harley", "ducati", "bmw motorrad",
            "ola electric", "ather", "simple energy", "revolt",
            "launch", "specs", "review", "price", "mileage", "cc", "bhp",
            "ev", "electric bike", "range", "charging", "recall", "racing",
            "motogp", "dakar", "superbike", "cruiser", "adventure"
        ]
        penalties = ["sponsored", "ad", "partner", "promoted"]

    class Sources:
        urls = [
            "https://www.bikewale.com/",
            "https://www.bikedekho.com/",
            "https://auto.ndtv.com/motorcycles",
            "https://www.motorbeam.com/",
            "https://rushlane.com/two-wheelers",
        ]

    class Paths:
        articles_dir = "./outputs/articles"
        images_dir = "./outputs/images"
        logs_dir = "./outputs/logs"
        db_path = "./data/newsbot.db"
        database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/newsbot")
        fallback_image_path = "./outputs/images/fallback-moto.jpg"
        excel_log_path = os.getenv("EXCEL_LOG_PATH", "./logs.xlsx")

    class App:
        port = int(os.getenv("PORT", "3001"))
        base_url = os.getenv("BASE_URL", "http://localhost:3001")
        site_name = os.getenv("SITE_NAME", "NewsBot")
        approver_emails = [e.strip() for e in os.getenv("APPROVER_EMAILS", "").split(",") if e.strip()]
        approval_secret = os.getenv("APPROVAL_SECRET", os.getenv("GEMINI_API_KEY", ""))

    class Cms:
        webhook_url = os.getenv("CMS_WEBHOOK_URL", "")
        api_key = os.getenv("CMS_API_KEY", "")

    class ImageSearch:
        use_gemini_search = os.getenv("USE_GEMINI_IMAGE_SEARCH", "1") == "1"
        serpapi_key = os.getenv("SERPAPI_API_KEY", "")
        timeout_seconds = float(os.getenv("IMAGE_SEARCH_TIMEOUT_SECONDS", "12"))
        max_candidates = int(os.getenv("IMAGE_MAX_CANDIDATES", "8"))
        max_output_bytes = int(os.getenv("IMAGE_MAX_OUTPUT_BYTES", str(200 * 1024)))
        overlay_text = os.getenv("IMAGE_OVERLAY_TEXT", "1") == "1"

    class Email:
        daily_limit = int(os.getenv("DAILY_EMAIL_LIMIT", "5"))

    class Observability:
        mlflow_enabled = os.getenv("MLFLOW_ENABLED", "1") == "1"
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "newsbot-blogs")
        usd_to_inr = float(os.getenv("USD_TO_INR", "83.0"))
        text_input_cost_usd_per_million = float(os.getenv("TEXT_INPUT_COST_USD_PER_MILLION", "0"))
        text_output_cost_usd_per_million = float(os.getenv("TEXT_OUTPUT_COST_USD_PER_MILLION", "0"))
        image_cost_usd = float(os.getenv("IMAGE_COST_USD", "0"))
        summary_max_chars = int(os.getenv("OBSERVABILITY_SUMMARY_MAX_CHARS", "280"))

CONFIG = Config()

CONFIG = Config()
