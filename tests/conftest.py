from __future__ import annotations

import os

os.environ.setdefault("API_KEY", "testkey")
os.environ.setdefault("TOKEN_DIR", "/tmp/garmin-tokens")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("CACHE_TTL_SECONDS", "1")
os.environ.setdefault("TZ", "America/New_York")
os.environ.setdefault("PORT", "8000")
