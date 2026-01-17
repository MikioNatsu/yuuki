from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.api.v1.router import router as v1_router
from app.core.config import Settings, get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware.access_log import AccessLogMiddleware
from app.core.middleware.rate_limit import RateLimitMiddleware
from app.core.middleware.request_id import RequestIdMiddleware
from app.core.middleware.security_headers import SecurityHeadersMiddleware
from app.infrastructure.cache.redis_client import close_redis_client, create_redis_client
from app.infrastructure.db.session import build_async_engine, build_sessionmaker
from app.infrastructure.llm.ollama_client import OllamaLLMClient
from app.infrastructure.vision.clip_recognizer import ClipAnimeRecognizer, ClipConfig
from app.repositories.anime_repository_sqlalchemy import SqlAlchemyAnimeRepository

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)

    Image.MAX_IMAGE_PIXELS = int(settings.max_image_pixels)

    docs_url = "/docs" if settings.docs_enabled else None
    redoc_url = "/redoc" if settings.docs_enabled else None
    openapi_url = "/openapi.json" if settings.docs_enabled else None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        await _startup(app, settings)
        try:
            yield
        finally:
            await _shutdown(app)

    app = FastAPI(
        title=settings.app_name,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
        allow_credentials=settings.cors_allow_credentials,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    return app


async def _startup(app: FastAPI, settings: Settings) -> None:
    engine: AsyncEngine = build_async_engine(settings)
    sessionmaker: async_sessionmaker = build_sessionmaker(engine)

    app.state.engine = engine
    app.state.sessionmaker = sessionmaker

    redis = await create_redis_client(settings)
    app.state.redis = redis

    http_client = httpx.AsyncClient(
        base_url=str(settings.ollama_base_url),
        timeout=httpx.Timeout(settings.ollama_timeout_seconds),
        headers={"Accept": "application/json"},
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    app.state.http_client = http_client
    app.state.llm_client = OllamaLLMClient(
        http_client=http_client,
        model=settings.ollama_model,
        temperature=settings.ollama_temperature,
        timeout_seconds=settings.ollama_timeout_seconds,
    )

    clip_cfg = ClipConfig(
        model_path=settings.clip_model_path,
        device=settings.clip_device,
        use_fp16=settings.clip_use_fp16,
        concurrency=settings.clip_concurrency,
        index_path=settings.clip_index_path,
        build_index_on_startup=settings.clip_index_build_on_startup,
        text_batch_size=settings.clip_text_batch_size,
    )
    vision = await ClipAnimeRecognizer.create(cfg=clip_cfg)
    app.state.vision_recognizer = vision

    titles_count = 0
    try:
        async with sessionmaker() as session:
            repo = SqlAlchemyAnimeRepository(session=session, timeout_seconds=settings.repository_timeout_seconds)
            titles = await repo.list_canonical_titles()
            titles_count = len(titles)
        if titles:
            await vision.initialize_index(titles=titles, rebuild=False)
        else:
            logger.warning("clip_index_skipped_no_titles")
    except Exception as exc:  # noqa: BLE001
        logger.exception("clip_index_init_failed", extra={"reason": str(exc)})

    logger.info("startup_complete", extra={"titles_indexed": titles_count, "redis_enabled": redis is not None})


async def _shutdown(app: FastAPI) -> None:
    http_client = getattr(app.state, "http_client", None)
    if http_client is not None:
        try:
            await http_client.aclose()
        except Exception:  # noqa: BLE001
            pass

    redis = getattr(app.state, "redis", None)
    await close_redis_client(redis)

    engine = getattr(app.state, "engine", None)
    if engine is not None:
        try:
            await engine.dispose()
        except Exception:  # noqa: BLE001
            pass


app = create_app()
