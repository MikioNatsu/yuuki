from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from fastapi import Request

_REQ_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_.]{7,63}$")


def is_valid_request_id(value: str) -> bool:
    return bool(_REQ_ID_RE.fullmatch(value))


def get_client_ip(request: Request, *, trusted_proxy_headers: bool) -> str:
    if trusted_proxy_headers:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            ip = xff.split(",")[0].strip()
            if ip:
                return ip
        xrip = request.headers.get("x-real-ip", "").strip()
        if xrip:
            return xrip

    client = request.client
    if client and client.host:
        return client.host
    return "-"


def normalize_public_url(url: str | None) -> str | None:
    if not isinstance(url, str):
        return None
    value = url.strip()
    if not value:
        return None
    if len(value) > 2048:
        return None
    if any(ch in value for ch in ("\r", "\n", "\t")):
        return None

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    return value
