from __future__ import annotations

from typing import Protocol

from app.domain.entities import AnimeLinks


class AnimeRepository(Protocol):
    async def get_by_canonical_title(self, canonical_title: str) -> AnimeLinks | None:
        ...

    async def list_canonical_titles(self) -> list[str]:
        ...
