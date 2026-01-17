from __future__ import annotations

from typing import Any, Protocol


class Cache(Protocol):
    async def get_json(self, key: str) -> Any | None:
        ...

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        ...
