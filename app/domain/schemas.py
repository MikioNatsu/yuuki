from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class AnimeCandidateOut(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    confidence: float = Field(ge=0.0, le=1.0)


class AnimeOut(BaseModel):
    canonical_title: str = Field(min_length=1, max_length=256)
    primary_url: str = Field(min_length=1, max_length=2048)
    official_url: str | None = Field(default=None, max_length=2048)
    platform_url: str | None = Field(default=None, max_length=2048)
    title_markdown: str = Field(min_length=1, max_length=2300)


class IdentifyAnimeResponseOk(BaseModel):
    status: Literal["ok"] = "ok"
    request_id: str
    message: str
    anime: AnimeOut


class IdentifyAnimeResponseUncertain(BaseModel):
    status: Literal["uncertain"] = "uncertain"
    request_id: str
    message: str
    candidates: list[AnimeCandidateOut]


IdentifyAnimeResponse = Annotated[
    Union[IdentifyAnimeResponseOk, IdentifyAnimeResponseUncertain],
    Field(discriminator="status"),
]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str
