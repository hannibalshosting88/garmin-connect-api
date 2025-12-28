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


def test_daily_returns_needs_login(monkeypatch, tmp_path: Path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.get(
        "/daily",
        params={"date": "2024-01-01", "mode": "normalized"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "needs_login"


def test_daily_schema_has_summary_object() -> None:
    from app.models import DailyNormalizedResponse

    summary = {
        "steps": 100,
        "calories_total_kcal": 2000,
        "calories_active_kcal": 300,
        "resting_hr_bpm": 50,
        "sleep_seconds": 20000,
        "sleep_score": 80,
        "stress_avg": 20,
        "body_battery_start": 60,
        "body_battery_end": 30,
        "hrv_status": "balanced",
        "hrv_value": 70.0,
        "intensity_minutes_moderate": 30,
        "intensity_minutes_vigorous": 0,
        "intensity_minutes_total": 30,
        "weight_lb": 175.2,
    }
    payload = DailyNormalizedResponse(
        date="2024-01-01",
        summary=summary,
        activities=[],
        links={
            "daily": "/daily?date=2024-01-01&mode=normalized",
            "sleep": "/sleep?date=2024-01-01&mode=normalized",
            "activities": "/activities?start=2024-01-01&end=2024-01-01&mode=normalized",
            "activity_detail_template": "/activities/{activityId}?mode=normalized",
            "stress": "/stress?date=2024-01-01&mode=normalized",
            "body_battery": "/body-battery?date=2024-01-01&mode=normalized",
            "hrv": "/hrv?date=2024-01-01&mode=normalized",
            "intensity_minutes": "/intensity-minutes?date=2024-01-01&mode=normalized",
        },
    ).model_dump()
    assert "summary" in payload
    assert "steps" not in payload
    assert payload["summary"]["steps"] == 100
