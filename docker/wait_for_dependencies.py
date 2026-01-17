from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Optional

import asyncpg
import redis.asyncio as redis_async


@dataclass(frozen=True)
class WaitConfig:
    postgres_dsn: str
    redis_dsn: str
    connect_timeout_seconds: float
    overall_timeout_seconds: float
    poll_interval_seconds: float


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _asyncpg_dsn(dsn: str) -> str:
    return dsn.replace("+asyncpg", "")


async def _wait_postgres(cfg: WaitConfig) -> None:
    dsn = _asyncpg_dsn(cfg.postgres_dsn)
    deadline = asyncio.get_event_loop().time() + cfg.overall_timeout_seconds
    last_err: Optional[BaseException] = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            conn = await asyncpg.connect(dsn=dsn, timeout=cfg.connect_timeout_seconds)
            try:
                await conn.execute("SELECT 1;")
            finally:
                await conn.close()
            return
        except BaseException as exc:  # noqa: BLE001
            last_err = exc
            await asyncio.sleep(cfg.poll_interval_seconds)
    raise RuntimeError("PostgreSQL is not reachable") from last_err


async def _wait_redis(cfg: WaitConfig) -> None:
    deadline = asyncio.get_event_loop().time() + cfg.overall_timeout_seconds
    last_err: Optional[BaseException] = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            client = redis_async.Redis.from_url(
                cfg.redis_dsn,
                socket_connect_timeout=cfg.connect_timeout_seconds,
                socket_timeout=cfg.connect_timeout_seconds,
                retry_on_timeout=True,
                health_check_interval=10,
            )
            try:
                await client.ping()
            finally:
                await client.close(close_connection_pool=True)
            return
        except BaseException as exc:  # noqa: BLE001
            last_err = exc
            await asyncio.sleep(cfg.poll_interval_seconds)
    raise RuntimeError("Redis is not reachable") from last_err


async def main() -> int:
    cfg = WaitConfig(
        postgres_dsn=_require_env("POSTGRES_DSN"),
        redis_dsn=_require_env("REDIS_DSN"),
        connect_timeout_seconds=float(os.getenv("WAIT_CONNECT_TIMEOUT_SECONDS", "2.0")),
        overall_timeout_seconds=float(os.getenv("WAIT_OVERALL_TIMEOUT_SECONDS", "60.0")),
        poll_interval_seconds=float(os.getenv("WAIT_POLL_INTERVAL_SECONDS", "1.0")),
    )

    await _wait_postgres(cfg)
    await _wait_redis(cfg)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
