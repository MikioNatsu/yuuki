from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import AnimeLinks
from app.domain.ports.anime_repository import AnimeRepository
from app.infrastructure.db.models import Anime


class SqlAlchemyAnimeRepository(AnimeRepository):
    def __init__(self, *, session: AsyncSession, timeout_seconds: float) -> None:
        self._session = session
        self._timeout_seconds = float(timeout_seconds)

    async def get_by_canonical_title(self, canonical_title: str) -> AnimeLinks | None:
        title = (canonical_title or "").strip()
        if not title:
            return None

        stmt = select(Anime).where(Anime.canonical_title == title).limit(1)
        result = await asyncio.wait_for(self._session.execute(stmt), timeout=self._timeout_seconds)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return AnimeLinks(
            canonical_title=row.canonical_title,
            official_url=row.official_url,
            platform_url=row.platform_url,
        )

    async def list_canonical_titles(self) -> list[str]:
        stmt = select(Anime.canonical_title)
        result = await asyncio.wait_for(self._session.execute(stmt), timeout=self._timeout_seconds)
        titles = [r[0] for r in result.all() if r and r[0]]
        titles = [t.strip() for t in titles if isinstance(t, str) and t.strip()]
        titles.sort()
        return titles
