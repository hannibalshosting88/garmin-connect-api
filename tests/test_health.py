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


def test_health_requires_api_key(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get("/health")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_api_key"


def test_health_reports_tokens(monkeypatch, tmp_path: Path) -> None:
    token_file = tmp_path / "token.json"
    token_file.write_text("{\"access_token\": \"stub\"}", encoding="utf-8")
    meta_file = tmp_path / "token_meta.json"
    meta_file.write_text("{\"last_refresh\": \"2024-01-01T12:00:00+00:00\"}", encoding="utf-8")
    client = _client(monkeypatch, tmp_path)
    response = client.get("/health", headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["auth"] in {"ok", "error"}
    assert payload["token_dir"] == str(tmp_path)
    assert payload["token_last_refresh"] is not None
