from __future__ import annotations

from contextvars import ContextVar

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")
locale_ctx_var: ContextVar[str] = ContextVar("locale", default="-")
client_ip_ctx_var: ContextVar[str] = ContextVar("client_ip", default="-")
