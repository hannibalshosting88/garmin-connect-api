from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    auth: Literal["ok", "needs_login", "error"]
    token_dir: str
    token_last_refresh: datetime | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "ok",
                    "version": "dev",
                    "auth": "ok",
                    "token_dir": "/data/tokens",
                    "token_last_refresh": "2024-01-01T12:00:00+00:00",
                }
            ]
        }
    }


class DailyActivityStub(BaseModel):
    activityId: int
    type: str | None = None
    name: str | None = None
    startTimeLocal: str | None = None
    duration_s: int | None = None
    distance_mi: float | None = None
    avg_speed_mph: float | None = None
    elevation_gain_ft: int | None = None


class DailyLinks(BaseModel):
    daily: str
    sleep: str
    activities: str
    activity_detail_template: str
    stress: str
    body_battery: str
    hrv: str
    intensity_minutes: str


class DailySummary(BaseModel):
    steps: int | None = None
    calories_total_kcal: int | None = None
    calories_active_kcal: int | None = None
    resting_hr_bpm: int | None = None
    sleep_seconds: int | None = None
    sleep_score: int | None = None
    stress_avg: int | None = None
    body_battery_start: int | None = None
    body_battery_end: int | None = None
    hrv_status: str | None = None
    hrv_value: float | None = None
    intensity_minutes_moderate: int | None = None
    intensity_minutes_vigorous: int | None = None
    intensity_minutes_total: int | None = None
    weight_lb: float | None = None


class DailyNormalizedResponse(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    summary: DailySummary
    activities: list[DailyActivityStub]
    links: DailyLinks

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "date": "2024-01-01",
                    "summary": {
                        "steps": 9342,
                        "calories_total_kcal": 2201,
                        "calories_active_kcal": 512,
                        "resting_hr_bpm": 52,
                        "sleep_seconds": 25140,
                        "sleep_score": 83,
                        "stress_avg": 28,
                        "body_battery_start": 63,
                        "body_battery_end": 18,
                        "hrv_status": "balanced",
                        "hrv_value": 68.2,
                        "intensity_minutes_moderate": 35,
                        "intensity_minutes_vigorous": 0,
                        "intensity_minutes_total": 35,
                        "weight_lb": 173.4,
                    },
                    "activities": [
                        {
                            "activityId": 123456789,
                            "type": "running",
                            "name": "Lunch Run",
                            "startTimeLocal": "2024-01-01 12:15:00",
                            "duration_s": 1800,
                            "distance_mi": 3.1,
                            "avg_speed_mph": 6.2,
                            "elevation_gain_ft": 210,
                        }
                    ],
                    "links": {
                        "daily": "/daily?date=2024-01-01&mode=normalized",
                        "sleep": "/sleep?date=2024-01-01&mode=normalized",
                        "activities": "/activities?start=2024-01-01&end=2024-01-01&mode=normalized",
                        "activity_detail_template": "/activities/{activityId}?mode=normalized",
                        "stress": "/stress?date=2024-01-01&mode=normalized",
                        "body_battery": "/body-battery?date=2024-01-01&mode=normalized",
                        "hrv": "/hrv?date=2024-01-01&mode=normalized",
                        "intensity_minutes": "/intensity-minutes?date=2024-01-01&mode=normalized",
                    },
                }
            ]
        }
    }


class SleepResponse(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    sleep_seconds: int | None = None
    sleep_score: int | None = None
    deep_sleep_seconds: int | None = None
    light_sleep_seconds: int | None = None
    rem_sleep_seconds: int | None = None
    awake_seconds: int | None = None


class StressResponse(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    stress_avg: int | None = None
    stress_max: int | None = None
    stress_seconds: int | None = None


class BodyBatteryResponse(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    body_battery_start: int | None = None
    body_battery_end: int | None = None
    body_battery_low: int | None = None
    body_battery_high: int | None = None


class HRVResponse(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    hrv_status: str | None = None
    hrv_value: float | None = None


class IntensityMinutesResponse(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    intensity_minutes_moderate: int | None = None
    intensity_minutes_vigorous: int | None = None
    intensity_minutes_total: int | None = None


class BodyWeightEntry(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    weight_lb: float | None = None


class BodyWeightResponse(BaseModel):
    start: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    latest_weight_lb: float | None = None
    weights: list[BodyWeightEntry]


class ActivitiesListItem(BaseModel):
    activityId: int
    type: str | None = None
    name: str | None = None
    startTimeLocal: str | None = None
    duration_s: int | None = None
    distance_mi: float | None = None
    avg_speed_mph: float | None = None
    elevation_gain_ft: int | None = None
    calories_kcal: int | None = None


class ActivitiesListResponse(BaseModel):
    start: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    activities: list[ActivitiesListItem]


class ActivityDetailResponse(BaseModel):
    activityId: int
    type: str | None = None
    name: str | None = None
    startTimeLocal: str | None = None
    duration_s: int | None = None
    distance_mi: float | None = None
    avg_speed_mph: float | None = None
    elevation_gain_ft: int | None = None
    calories_kcal: int | None = None
    avg_hr_bpm: int | None = None
    max_hr_bpm: int | None = None


class RawResponse(BaseModel):
    data: dict[str, Any]
