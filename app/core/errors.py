from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AppError(Exception):
    code: str
    http_status: int
    log_detail: str | None = None
    extra: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.log_detail or self.code


class InvalidImageError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="invalid_image", http_status=400, log_detail=log_detail)


class ImageTooLargeError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="image_too_large", http_status=413, log_detail=log_detail)


class UnsupportedImageTypeError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="unsupported_image_type", http_status=415, log_detail=log_detail)


class ImageDimensionsExceededError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="image_dimensions_exceeded", http_status=413, log_detail=log_detail)


class RequestInvalidError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="request_invalid", http_status=422, log_detail=log_detail)


class RateLimitedError(AppError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            code="rate_limited",
            http_status=429,
            log_detail="rate limited",
            extra={"retry_after_seconds": retry_after_seconds},
        )


class ServiceUnavailableError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="service_unavailable", http_status=503, log_detail=log_detail)


class RecognitionUnavailableError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="recognition_unavailable", http_status=503, log_detail=log_detail)


class AnimeNotFoundError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="anime_not_found", http_status=404, log_detail=log_detail)


class LinksNotFoundError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="links_not_found", http_status=404, log_detail=log_detail)


class LLMUnavailableError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="llm_unavailable", http_status=503, log_detail=log_detail)


class InternalError(AppError):
    def __init__(self, log_detail: str | None = None) -> None:
        super().__init__(code="internal_error", http_status=500, log_detail=log_detail)
