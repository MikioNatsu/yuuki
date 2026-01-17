from __future__ import annotations

from typing import Protocol

from app.domain.entities import AnimeCandidate


class VisionRecognizer(Protocol):
    async def recognize(self, image_bytes: bytes, *, top_k: int) -> list[AnimeCandidate]:
        ...
