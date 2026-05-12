# FILE: src/utils/error_handler.py | PURPOSE: Centralized error classes and handler utilities

class AppError(Exception):
    def __init__(self, message: str, code: str = "APP_ERROR", status_code: int = 500, details: dict = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}

class GeminiParseError(AppError):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "GEMINI_PARSE_ERROR", 502, details)

class GeminiInputError(AppError):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "GEMINI_INPUT_ERROR", 400, details)

class DBError(AppError):
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "DB_ERROR", 500, details)

def handle_error(error: Exception, logger, context: dict = None) -> AppError:
    context = context or {}
    
    if isinstance(error, AppError):
        normalized = error
    else:
        normalized = AppError(str(error), "UNEXPECTED_ERROR", 500, context)

    logger.error(normalized.args[0], extra={
        "context": context,
        "code": normalized.code,
        "status_code": normalized.status_code,
        "details": normalized.details
    }, exc_info=not isinstance(error, AppError))

    return normalized
