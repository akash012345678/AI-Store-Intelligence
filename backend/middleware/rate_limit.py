import time
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Globally active, in-memory IP-based rate limiting middleware."""
    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        # Dict mapping IP -> list of request timestamps
        self.ip_records = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()

        # Prune timestamps older than 60 seconds
        timestamps = self.ip_records[client_ip]
        self.ip_records[client_ip] = [t for t in timestamps if now - t < 60]

        if len(self.ip_records[client_ip]) >= self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "message": "Too many requests. Please slow down.",
                    "error_code": "RATE_LIMIT_EXCEEDED"
                }
            )

        self.ip_records[client_ip].append(now)
        return await call_next(request)
