from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.core.config import Settings
from app.core.deps import anime_service_dep, locale_dep, settings_dep
from app.core.i18n import t
from app.core.image_validation import parse_and_validate_image_bytes, read_upload_limited
from app.domain.entities import IdentificationUncertain
from app.domain.schemas import (
    AnimeCandidateOut,
    AnimeOut,
    IdentifyAnimeResponse,
    IdentifyAnimeResponseOk,
    IdentifyAnimeResponseUncertain,
)
from app.services.anime_identification_service import AnimeIdentificationService

router = APIRouter()


@router.post("/anime/identify", response_model=IdentifyAnimeResponse)
async def identify_anime(
    request: Request,
    file: UploadFile = File(...),
    locale: str = Depends(locale_dep),
    settings: Settings = Depends(settings_dep),
    service: AnimeIdentificationService = Depends(anime_service_dep),
) -> IdentifyAnimeResponse:
    try:
        raw, sha256_hex = await read_upload_limited(
            upload=file,
            max_bytes=settings.max_upload_bytes,
            chunk_size=settings.upload_read_chunk_size,
        )
        image = parse_and_validate_image_bytes(
            data=raw,
            sha256_hex=sha256_hex,
            allowed_mime_types=settings.allowed_image_mime_types,
            max_pixels=settings.max_image_pixels,
            max_width=settings.max_image_width,
            max_height=settings.max_image_height,
        )
    finally:
        try:
            await file.close()
        except Exception:  # noqa: BLE001
            pass

    rid = getattr(request.state, "request_id", "-") or "-"

    result = await service.identify(image=image, locale=locale)
    if isinstance(result, IdentificationUncertain):
        candidates_out = [
            AnimeCandidateOut(title=c.title, confidence=c.confidence) for c in (result.candidates[:3] if result.candidates else [])
        ]
        return IdentifyAnimeResponseUncertain(
            request_id=rid,
            message=t(locale, "uncertain"),
            candidates=candidates_out,
        )

    anime_out = AnimeOut(
        canonical_title=result.canonical_title,
        primary_url=result.primary_url,
        official_url=result.official_url,
        platform_url=result.platform_url,
        title_markdown=result.title_markdown,
    )
    return IdentifyAnimeResponseOk(
        request_id=rid,
        message=result.message,
        anime=anime_out,
    )
