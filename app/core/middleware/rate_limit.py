from __future__ import annotations

import asyncio
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.errors import RateLimitedError
from app.core.security import get_client_ip


_LUA_INCR_EXPIRE = """    local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return await call_next(request)

        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            return await call_next(request)

        ip = get_client_ip(request, trusted_proxy_headers=settings.trusted_proxy_headers)
        window = int(settings.rate_limit_window_seconds)
        limit = int(settings.rate_limit_requests)
        now = int(time.time())
        bucket = now // window
        key = f"{settings.rate_limit_key_prefix}{ip}:{bucket}"
        ttl = window + 1

        try:
            current = await asyncio.wait_for(
                redis.eval(_LUA_INCR_EXPIRE, 1, key, ttl),
                timeout=settings.redis_operation_timeout_seconds,
            )
            current_int = int(current)
        except Exception:  # noqa: BLE001
            return await call_next(request)

        if current_int > limit:
            retry_after = window - (now % window)
            raise RateLimitedError(retry_after_seconds=retry_after)

        return await call_next(request)
