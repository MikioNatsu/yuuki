from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.context import client_ip_ctx_var, locale_ctx_var, request_id_ctx_var
from app.core.config import Settings


_RESERVED_ATTRS: set[str] = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
}

_DSN_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(postgres(?:ql)?(?:\+asyncpg)?://)([^:/\s]+):([^@/\s]+)@"), r"\1\2:***@"),
    (re.compile(r"(redis(?:\+ssl)?://)(:)?([^@/\s]+)@"), r"\1:***@"),
    (re.compile(r"(?i)(password=)([^\s&]+)"), r"\1***"),
]


def _redact_secrets(value: str) -> str:
    out = value
    for pattern, repl in _DSN_REDACTIONS:
        out = pattern.sub(repl, out)
    return out


def _sanitize_any(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_secrets(value)
    if isinstance(value, dict):
        return {str(k): _sanitize_any(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_any(v) for v in value]
    return value


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx_var.get()
        record.locale = locale_ctx_var.get()
        record.client_ip = client_ip_ctx_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = _redact_secrets(record.getMessage())

        base: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": msg,
            "request_id": getattr(record, "request_id", "-"),
            "locale": getattr(record, "locale", "-"),
            "client_ip": getattr(record, "client_ip", "-"),
        }

        extras: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in _RESERVED_ATTRS or key.startswith("_"):
                continue
            if key in ("request_id", "locale", "client_ip"):
                continue
            extras[key] = _sanitize_any(value)

        if extras:
            base.update(extras)

        if record.exc_info:
            base["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            exc_text = self.formatException(record.exc_info)
            base["exc"] = _redact_secrets(exc_text)

        return json.dumps(base, ensure_ascii=False, separators=(",", ":"))


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.addFilter(RequestContextFilter())

    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))

    root.addHandler(handler)

    logging.getLogger("uvicorn").handlers.clear()
    logging.getLogger("uvicorn.error").handlers.clear()
    logging.getLogger("uvicorn.access").handlers.clear()

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.propagate = True
        logger.setLevel(level)
