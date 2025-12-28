from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.garmin_client import get_garmin_client
from app.main import app
from app.settings import get_settings


def _client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("TOKEN_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_garmin_client.cache_clear()
    return TestClient(app)


def test_rejects_invalid_api_key(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/health", headers={"X-API-Key": "nope"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "invalid_api_key"
