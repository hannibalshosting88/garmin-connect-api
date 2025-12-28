from __future__ import annotations

import json
import time
from typing import Any


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        self._store[key] = (expires_at, value)


def make_cache_key(route_name: str, params: dict[str, Any], mode: str) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return f"{route_name}:{mode}:{payload}"
