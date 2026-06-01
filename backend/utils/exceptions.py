from fastapi import Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

class PurpleInsightException(Exception):
    """Base exception for all system exceptions."""
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(message)

class ResourceNotFoundException(PurpleInsightException):
    """Exception raised when a requested resource is missing."""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, "NOT_FOUND", 404)

class BadRequestException(PurpleInsightException):
    """Exception raised on invalid parameter inputs or states."""
    def __init__(self, message: str = "Bad request"):
        super().__init__(message, "BAD_REQUEST", 400)

class UnauthorizedException(PurpleInsightException):
    """Exception raised when credentials are missing or invalid."""
    def __init__(self, message: str = "Unauthorized access"):
        super().__init__(message, "UNAUTHORIZED", 401)


# Standardized FastAPI Handlers

async def system_exception_handler(request: Request, exc: PurpleInsightException) -> JSONResponse:
    """Handles all custom PurpleInsightException exceptions, returning formatted JSON."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "error_code": exc.error_code
        }
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handles standard Starlette/FastAPI HTTPExceptions, mapping to standard JSON."""
    error_code = "BAD_REQUEST"
    if exc.status_code == 404:
        error_code = "NOT_FOUND"
    elif exc.status_code == 401:
        error_code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        error_code = "FORBIDDEN"
    elif exc.status_code == 429:
        error_code = "RATE_LIMIT_EXCEEDED"
    elif exc.status_code >= 500:
        error_code = "INTERNAL_SERVER_ERROR"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "error_code": error_code
        }
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles validation errors (e.g. Pydantic constraints breaches), returning standard error keys."""
    # Concatenate error summaries
    details = []
    for error in exc.errors():
        loc = " -> ".join(map(str, error.get("loc", [])))
        msg = error.get("msg", "invalid input")
        details.append(f"[{loc}]: {msg}")
    
    summary = "; ".join(details)
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": f"Validation error: {summary}",
            "error_code": "VALIDATION_ERROR"
        }
    )

async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled backend exceptions, preventing code leaks."""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"An unexpected error occurred: {str(exc)}",
            "error_code": "INTERNAL_SERVER_ERROR"
        }
    )
