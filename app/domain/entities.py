from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    mime_type: str
    sha256: str
    width: int
    height: int


@dataclass(frozen=True)
class AnimeCandidate:
    title: str
    confidence: float


@dataclass(frozen=True)
class AnimeLinks:
    canonical_title: str
    official_url: str | None
    platform_url: str | None


@dataclass(frozen=True)
class IdentificationSuccess:
    canonical_title: str
    primary_url: str
    official_url: str | None
    platform_url: str | None
    title_markdown: str
    message: str


@dataclass(frozen=True)
class IdentificationUncertain:
    candidates: list[AnimeCandidate]
