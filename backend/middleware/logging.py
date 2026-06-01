"""
backend/middleware/logging.py
─────────────────────────────
Structured HTTP access-log middleware.

Logs every request with:
  - RequestID  : UUID from RequestContextMiddleware context var
  - Method     : HTTP verb
  - Path       : URL path (without query string)
  - StatusCode : response status code
  - Latency    : end-to-end response time in milliseconds
  - ClientIP   : remote host IP
  - UserAgent  : request User-Agent header (first 80 chars)

Attaches the following response headers:
  - X-Process-Time : latency string (e.g. "12.34ms")
  - X-Request-ID   : trace UUID for log correlation

Engineering note:
  This middleware uses Starlette's BaseHTTPMiddleware. For extreme throughput
  (> 10k RPS) consider switching to a pure ASGI middleware to avoid the
  stream-buffering overhead introduced by BaseHTTPMiddleware.
"""

from __future__ import annotations

import time
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from backend.middleware.request_context import get_request_id

logger = logging.getLogger("PurpleInsight.AccessLog")
logger.setLevel(logging.INFO)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Structured HTTP access-log middleware.

    Records one log line per request containing all tracing dimensions
    required for SLA monitoring and debugging without relying on external
    APM tooling at the infrastructure layer.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()

        method     = request.method
        path       = request.url.path
        client_ip  = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")[:80]
        req_id     = get_request_id()

        try:
            response = await call_next(request)
            latency_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "REQUEST  reqid=%-36s  method=%-6s  status=%d  "
                "path=%-40s  latency=%.2fms  ip=%s  ua=%s",
                req_id,
                method,
                response.status_code,
                path,
                latency_ms,
                client_ip,
                user_agent,
            )

            response.headers["X-Process-Time"] = f"{latency_ms:.2f}ms"
            response.headers["X-Request-ID"]   = req_id
            return response

        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "REQUEST  reqid=%-36s  method=%-6s  status=500  "
                "path=%-40s  latency=%.2fms  ip=%s  error=%s",
                req_id,
                method,
                path,
                latency_ms,
                client_ip,
                str(exc),
            )
            raise
