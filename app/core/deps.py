from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.context import client_ip_ctx_var, locale_ctx_var
from app.core.i18n import infer_locale_from_headers
from app.core.security import get_client_ip
from app.domain.ports.anime_repository import AnimeRepository
from app.domain.ports.cache import Cache
from app.domain.ports.llm import LLMClient
from app.domain.ports.vision import VisionRecognizer
from app.infrastructure.cache.redis_client import NullCache, RedisCache
from app.infrastructure.llm.ollama_client import OllamaLLMClient
from app.infrastructure.vision.clip_recognizer import ClipAnimeRecognizer
from app.repositories.anime_repository_sqlalchemy import SqlAlchemyAnimeRepository
from app.services.anime_identification_service import AnimeIdentificationService, AnimeIdentificationServiceConfig


def settings_dep() -> Settings:
    return get_settings()


def locale_dep(request: Request, settings: Settings = Depends(settings_dep)) -> str:
    locale = infer_locale_from_headers(
        request.headers,
        default_locale=settings.default_locale,
        locale_header=settings.locale_header,
    )
    request.state.locale = locale
    locale_ctx_var.set(locale)

    ip = get_client_ip(request, trusted_proxy_headers=settings.trusted_proxy_headers)
    client_ip_ctx_var.set(ip)

    return locale


def _sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    sm: async_sessionmaker[AsyncSession] | None = getattr(request.app.state, "sessionmaker", None)
    if sm is None:
        raise RuntimeError("DB sessionmaker is not initialized")
    return sm


async def db_session_dep(request: Request) -> AsyncGenerator[AsyncSession, None]:
    sm = _sessionmaker(request)
    async with sm() as session:
        yield session


def cache_dep(request: Request, settings: Settings = Depends(settings_dep)) -> Cache:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return NullCache()
    return RedisCache(redis=redis, operation_timeout_seconds=settings.redis_operation_timeout_seconds)


def anime_repository_dep(
    session: AsyncSession = Depends(db_session_dep),
    settings: Settings = Depends(settings_dep),
) -> AnimeRepository:
    return SqlAlchemyAnimeRepository(session=session, timeout_seconds=settings.repository_timeout_seconds)


def vision_recognizer_dep(request: Request) -> VisionRecognizer:
    recognizer: ClipAnimeRecognizer | None = getattr(request.app.state, "vision_recognizer", None)
    if recognizer is None:
        raise RuntimeError("Vision recognizer is not initialized")
    return recognizer


def llm_client_dep(request: Request) -> LLMClient:
    client: OllamaLLMClient | None = getattr(request.app.state, "llm_client", None)
    if client is None:
        raise RuntimeError("LLM client is not initialized")
    return client


def anime_service_dep(
    settings: Settings = Depends(settings_dep),
    cache: Cache = Depends(cache_dep),
    repo: AnimeRepository = Depends(anime_repository_dep),
    vision: VisionRecognizer = Depends(vision_recognizer_dep),
    llm: LLMClient = Depends(llm_client_dep),
) -> AnimeIdentificationService:
    cfg = AnimeIdentificationServiceConfig(
        confidence_threshold=settings.clip_confidence_threshold,
        vision_top_k=settings.clip_top_k,
        cache_ttl_seconds=settings.redis_cache_ttl_seconds,
        image_dedupe_ttl_seconds=settings.redis_image_dedupe_ttl_seconds,
        clip_inference_timeout_seconds=settings.clip_inference_timeout_seconds,
    )
    return AnimeIdentificationService(config=cfg, cache=cache, repository=repo, vision=vision, llm=llm)
