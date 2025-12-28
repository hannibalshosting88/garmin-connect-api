from __future__ import annotations

from fastapi import Header

from app.errors import APIError
from app.settings import get_settings


def api_key_guard(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    settings = get_settings()
    if not x_api_key:
        raise APIError(401, "missing_api_key", "X-API-Key header is required")
    if x_api_key != settings.api_key:
        raise APIError(403, "invalid_api_key", "X-API-Key is invalid")
