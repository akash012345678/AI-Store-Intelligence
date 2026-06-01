import contextvars
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var = contextvars.ContextVar("request_id", default="")

def get_request_id() -> str:
    """Retrieves the request ID assigned to the current thread-safe context."""
    return request_id_var.get()

class RequestContextMiddleware(BaseHTTPMiddleware):
    """Enriches the ASGI request context with a unique UUID for comprehensive request tracing."""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Pull request ID if provided or generate a fresh UUID
        req_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        token = request_id_var.set(req_id)
        
        request.state.request_id = req_id
        response: Response = await call_next(request)
        response.headers["x-request-id"] = req_id
        
        request_id_var.reset(token)
        return response
