from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis_async

from app.core.config import Settings
from app.domain.ports.cache import Cache

logger = logging.getLogger(__name__)


async def create_redis_client(settings: Settings) -> redis_async.Redis | None:
    dsn = settings.redis_dsn_plain()
    client = redis_async.Redis.from_url(
        dsn,
        socket_connect_timeout=float(settings.redis_connect_timeout_seconds),
        socket_timeout=float(settings.redis_operation_timeout_seconds),
        retry_on_timeout=True,
        health_check_interval=10,
        decode_responses=False,
    )
    try:
        await asyncio.wait_for(client.ping(), timeout=float(settings.redis_connect_timeout_seconds))
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis_unavailable", extra={"reason": str(exc)})
        try:
            await client.close(close_connection_pool=True)
        except Exception:  # noqa: BLE001
            pass
        return None
    return client


async def close_redis_client(client: redis_async.Redis | None) -> None:
    if client is None:
        return
    try:
        await client.close(close_connection_pool=True)
    except Exception:  # noqa: BLE001
        return


class RedisCache(Cache):
    def __init__(self, *, redis: redis_async.Redis, operation_timeout_seconds: float) -> None:
        self._redis = redis
        self._timeout = float(operation_timeout_seconds)

    async def get_json(self, key: str) -> Any | None:
        raw = await asyncio.wait_for(self._redis.get(key), timeout=self._timeout)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="strict")
        else:
            text = str(raw)
        return json.loads(text)

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        await asyncio.wait_for(self._redis.set(key, payload.encode("utf-8"), ex=int(ttl_seconds)), timeout=self._timeout)


class NullCache(Cache):
    async def get_json(self, key: str) -> Any | None:  # noqa: ARG002
        return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:  # noqa: ARG002
        return
