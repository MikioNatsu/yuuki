from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.errors import AppError, InternalError
from app.core.i18n import infer_locale_from_headers, t

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-") or "-"


def _locale(request: Request) -> str:
    settings = get_settings()
    return getattr(request.state, "locale", "") or infer_locale_from_headers(
        request.headers,
        default_locale=settings.default_locale,
        locale_header=settings.locale_header,
    )


def _error_envelope(*, code: str, message: str, request_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}, "request_id": request_id}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        locale = _locale(request)
        rid = _request_id(request)
        payload = _error_envelope(code=exc.code, message=t(locale, exc.code), request_id=rid)

        headers: dict[str, str] = {}
        if exc.code == "rate_limited" and exc.extra and "retry_after_seconds" in exc.extra:
            headers["Retry-After"] = str(int(exc.extra["retry_after_seconds"]))

        if exc.http_status >= 500:
            logger.warning("app_error", extra={"code": exc.code, "request_id": rid}, exc_info=exc)
        else:
            logger.info("app_error", extra={"code": exc.code, "request_id": rid})

        return JSONResponse(status_code=exc.http_status, content=payload, headers=headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        locale = _locale(request)
        rid = _request_id(request)

        if exc.status_code == 404:
            code = "not_found"
        elif exc.status_code == 405:
            code = "method_not_allowed"
        else:
            code = "request_invalid"

        logger.info("http_exception", extra={"code": code, "status": exc.status_code, "request_id": rid})
        payload = _error_envelope(code=code, message=t(locale, code), request_id=rid)
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:  # noqa: ARG001
        locale = _locale(request)
        rid = _request_id(request)
        logger.info("request_validation_error", extra={"request_id": rid})
        payload = _error_envelope(code="request_invalid", message=t(locale, "request_invalid"), request_id=rid)
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        rid = _request_id(request)
        locale = _locale(request)
        logger.exception("unhandled_exception", extra={"request_id": rid})
        safe = InternalError()
        payload = _error_envelope(code=safe.code, message=t(locale, safe.code), request_id=rid)
        return JSONResponse(status_code=safe.http_status, content=payload)
