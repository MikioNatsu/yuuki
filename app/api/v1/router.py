from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes.anime import router as anime_router
from app.api.v1.routes.health import router as health_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(anime_router, tags=["anime"])
