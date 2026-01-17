from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import request_id_ctx_var
from app.core.security import is_valid_request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    header_name = "X-Request-ID"

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        incoming = (request.headers.get(self.header_name) or "").strip()
        rid = incoming if incoming and is_valid_request_id(incoming) else uuid.uuid4().hex
        request.state.request_id = rid
        request_id_ctx_var.set(rid)

        response = await call_next(request)
        response.headers[self.header_name] = rid
        return response
