from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    api_key: str = Field(..., alias="API_KEY")
    token_dir: str = Field(..., alias="TOKEN_DIR")
    garmin_email: str | None = Field(None, alias="GARMIN_EMAIL")
    garmin_password: str | None = Field(None, alias="GARMIN_PASSWORD")
    tz: str = Field("UTC", alias="TZ")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    cache_ttl_seconds: int = Field(300, alias="CACHE_TTL_SECONDS")
    port: int = Field(8000, alias="PORT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
