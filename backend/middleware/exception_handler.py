"""
backend/middleware/exception_handler.py
────────────────────────────────────────
Centralised exception handler registration for FastAPI.

Maps all exception types to structured JSON error envelopes:

  PurpleInsightException  → HTTP 400 (application-level domain errors)
  HTTPException           → Preserves original status code (4xx / 5xx)
  RequestValidationError  → HTTP 422 (input validation failures)
  Exception               → HTTP 500 (unhandled errors, stack-safe logging)

All responses share the ``ErrorResponse`` envelope:
  {
    "success": false,
    "request_id": "<UUID>",
    "errors": [
      { "field": "...", "message": "...", "code": "..." }
    ]
  }

Engineering note:
  Registering these handlers here (rather than inline in main.py) keeps the
  exception-handling concern isolated and independently testable.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.utils.exceptions import PurpleInsightException
from backend.middleware.request_context import get_request_id

logger = logging.getLogger("PurpleInsight.ExceptionHandler")


def _build_error_response(
    request_id: str,
    errors: list[dict],
    status_code: int,
) -> JSONResponse:
    """Constructs a standardised JSON error envelope."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "request_id": request_id,
            "errors": errors,
        },
    )


async def _handle_purpleinsight_exception(
    request: Request, exc: PurpleInsightException
) -> JSONResponse:
    """Converts domain-layer ``PurpleInsightException`` to HTTP 400."""
    req_id = get_request_id()
    logger.warning(
        "PurpleInsightException reqid=%s path=%s message=%s",
        req_id, request.url.path, str(exc),
    )
    return _build_error_response(
        request_id=req_id,
        errors=[{"field": None, "message": str(exc), "code": "DOMAIN_ERROR"}],
        status_code=status.HTTP_400_BAD_REQUEST,
    )


async def _handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Wraps Starlette/FastAPI ``HTTPException`` in the standard error envelope."""
    req_id = get_request_id()
    logger.warning(
        "HTTPException reqid=%s path=%s status=%d detail=%s",
        req_id, request.url.path, exc.status_code, exc.detail,
    )
    return _build_error_response(
        request_id=req_id,
        errors=[{"field": None, "message": str(exc.detail), "code": "HTTP_ERROR"}],
        status_code=exc.status_code,
    )


async def _handle_validation_exception(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Converts Pydantic v2 ``RequestValidationError`` to a flat, human-readable
    422 response listing each failing field and its error message.
    """
    req_id = get_request_id()
    errors = []
    for error in exc.errors():
        field_path = ".".join(str(loc) for loc in error.get("loc", []))
        errors.append({
            "field": field_path or None,
            "message": error.get("msg", "Validation error"),
            "code": error.get("type", "VALIDATION_ERROR").upper(),
        })

    logger.warning(
        "ValidationError reqid=%s path=%s errors=%s",
        req_id, request.url.path, errors,
    )
    return _build_error_response(
        request_id=req_id,
        errors=errors,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def _handle_global_exception(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all handler for unhandled exceptions.

    Logs the full stack trace at ERROR level and returns HTTP 500.
    Deliberately avoids exposing internal exception details to the client
    to prevent information leakage.
    """
    req_id = get_request_id()
    logger.exception(
        "UnhandledException reqid=%s path=%s",
        req_id, request.url.path,
    )
    return _build_error_response(
        request_id=req_id,
        errors=[{
            "field": None,
            "message": "An internal server error occurred. Please try again later.",
            "code": "INTERNAL_SERVER_ERROR",
        }],
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Registers all exception handlers on the FastAPI application instance.

    Call this once during application startup (in ``create_app``).
    """
    app.add_exception_handler(PurpleInsightException, _handle_purpleinsight_exception)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_exception)
    app.add_exception_handler(Exception, _handle_global_exception)
    logger.info("Registered global exception handlers [4 handlers active].")
