from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.responses import Response

from app.deps import api_key_guard
from app.errors import (
    APIError,
    GarminAuthFailure,
    MissingGarminAuth,
    UpstreamTimeout,
    register_exception_handlers,
)
from app.garmin_client import get_garmin_client
from app.cache import TTLCache, make_cache_key
from app import normalize
from app.settings import get_settings

logger = logging.getLogger("garmin-service")
cache = TTLCache()

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
MODE_PATTERN = r"^(normalized|raw)$"


def _resolve_version() -> str:
    # 1) Preferred: semantic version injected at build/runtime (CI)
    v = os.getenv("VERSION")
    if v and v.strip():
        return v.strip()

    # 2) Fallback: git SHA injected at build/runtime
    sha = os.getenv("VCS_REF") or os.getenv("GIT_SHA")
    if sha and sha.strip():
        return sha.strip()

    # 3) Optional local fallback: read from .git (dev only)
    sha_fs = _read_git_sha()
    if sha_fs:
        return sha_fs

    # 4) Absolute last resort
    return "dev"


def _read_git_sha() -> str | None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    head_path = os.path.join(root, ".git", "HEAD")
    try:
        with open(head_path, "r", encoding="utf-8") as handle:
            head = handle.read().strip()
    except OSError:
        return None
    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1].strip()
        ref_path = os.path.join(root, ".git", ref)
        try:
            with open(ref_path, "r", encoding="utf-8") as handle:
                sha = handle.read().strip()
        except OSError:
            return None
    else:
        sha = head
    if sha:
        return sha[:7]
    return None


def _not_implemented() -> None:
    raise APIError(503, "not_implemented", "Endpoint not implemented")


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise APIError(400, "invalid_date", f"Invalid {field} date") from exc


def _validate_range(start: str, end: str) -> None:
    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")
    if start_date > end_date:
        raise APIError(400, "invalid_range", "Start date must be before end date")


def _error_code_from_exc(exc: Exception) -> str | None:
    if isinstance(exc, APIError):
        return exc.code
    if isinstance(exc, MissingGarminAuth):
        return "needs_login"
    if isinstance(exc, GarminAuthFailure):
        return "garmin_auth_failure"
    if isinstance(exc, UpstreamTimeout):
        return "upstream_timeout"
    return None


def _get_first_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _activity_type(activity: dict[str, Any]) -> str | None:
    activity_type = activity.get("activityType") or {}
    if isinstance(activity_type, dict):
        return (
            activity_type.get("typeKey")
            or activity_type.get("type")
            or activity_type.get("typeName")
            or activity_type.get("typeId")
        )
    if isinstance(activity_type, str):
        return activity_type
    return activity.get("type")


def _activity_name(activity: dict[str, Any]) -> str | None:
    return activity.get("activityName") or activity.get("name")


def _activity_start_time(activity: dict[str, Any]) -> str | None:
    return activity.get("startTimeLocal") or activity.get("startTimeGMT") or activity.get("startTime")


def _activity_duration_s(activity: dict[str, Any]) -> int | None:
    value = _get_first_value(activity, ("duration", "durationInSeconds", "durationSeconds"))
    if isinstance(value, (int, float)):
        if value > 10_000:
            return int(round(value / 1000))
        return int(round(value))
    return None


def _activity_distance_meters(activity: dict[str, Any]) -> float | None:
    value = _get_first_value(
        activity, ("distance", "distanceMeters", "distanceInMeters", "distanceMetersValue")
    )
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _activity_avg_speed_mps(activity: dict[str, Any]) -> float | None:
    value = _get_first_value(activity, ("averageSpeed", "avgSpeed", "averageSpeedMps"))
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _activity_elevation_gain_m(activity: dict[str, Any]) -> float | None:
    value = _get_first_value(
        activity,
        ("elevationGain", "totalElevationGain", "elevationGainInMeters", "totalElevationGainMeters"),
    )
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _activity_calories(activity: dict[str, Any]) -> int | None:
    value = _get_first_value(activity, ("calories", "caloriesBurned", "totalCalories"))
    if isinstance(value, (int, float)):
        return int(round(value))
    return None


def _normalize_activity_stub(activity: dict[str, Any]) -> dict[str, Any]:
    distance_meters = _activity_distance_meters(activity)
    avg_speed_mps = _activity_avg_speed_mps(activity)
    elevation_m = _activity_elevation_gain_m(activity)
    activity_id = _get_first_value(activity, ("activityId", "activity_id"))
    activity_id_value = int(activity_id) if isinstance(activity_id, (int, float, str)) else None
    return {
        "activityId": activity_id_value,
        "type": _activity_type(activity),
        "name": _activity_name(activity),
        "startTimeLocal": _activity_start_time(activity),
        "duration_s": _activity_duration_s(activity),
        "distance_mi": normalize.distance_mi_always(distance_meters) if distance_meters is not None else None,
        "avg_speed_mph": (
            normalize.round_speed_mph(normalize.mps_to_mph(avg_speed_mps))
            if avg_speed_mps is not None
            else None
        ),
        "elevation_gain_ft": (
            normalize.round_elevation_ft(normalize.m_to_ft(elevation_m)) if elevation_m is not None else None
        ),
    }


def _normalize_activity_list_item(activity: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_activity_stub(activity)
    payload["calories_kcal"] = _activity_calories(activity)
    return payload


def _normalize_activity_detail(activity: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_activity_list_item(activity)
    payload["avg_hr_bpm"] = _get_first_value(activity, ("averageHR", "avgHr", "avgHeartRate"))
    payload["max_hr_bpm"] = _get_first_value(activity, ("maxHR", "maxHeartRate"))
    return payload


def _extract_sleep_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload or not isinstance(payload, dict):
        return {}
    daily = payload.get("dailySleepDTO") or payload
    if not isinstance(daily, dict):
        return {}
    sleep_seconds = _get_first_value(daily, ("sleepTimeSeconds", "sleepTime", "sleepSeconds"))
    score = _get_first_value(daily, ("sleepScore", "overallSleepScore"))
    return {
        "sleep_seconds": int(sleep_seconds) if isinstance(sleep_seconds, (int, float)) else None,
        "sleep_score": int(score) if isinstance(score, (int, float)) else None,
    }


def _extract_stress_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload or not isinstance(payload, dict):
        return {}
    avg = _get_first_value(payload, ("avgStressLevel", "avgStress", "averageStressLevel"))
    return {"stress_avg": int(avg) if isinstance(avg, (int, float)) else None}


def _extract_body_battery_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload or not isinstance(payload, dict):
        return {}
    start = _get_first_value(payload, ("bodyBatteryStart", "bodyBatteryBeginning"))
    end = _get_first_value(payload, ("bodyBatteryEnd", "bodyBatteryEnding", "bodyBatteryValue"))
    return {
        "body_battery_start": int(start) if isinstance(start, (int, float)) else None,
        "body_battery_end": int(end) if isinstance(end, (int, float)) else None,
    }


def _extract_hrv_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload or not isinstance(payload, dict):
        return {}
    status = _get_first_value(payload, ("status", "hrvStatus"))
    value = _get_first_value(payload, ("value", "hrvValue"))
    return {"hrv_status": status, "hrv_value": float(value) if isinstance(value, (int, float)) else None}


def _extract_intensity_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload or not isinstance(payload, dict):
        return {}
    moderate = _get_first_value(payload, ("moderateIntensityMinutes", "moderateMinutes"))
    vigorous = _get_first_value(payload, ("vigorousIntensityMinutes", "vigorousMinutes"))
    total = _get_first_value(payload, ("totalIntensityMinutes", "totalMinutes"))
    return {
        "intensity_minutes_moderate": int(moderate) if isinstance(moderate, (int, float)) else None,
        "intensity_minutes_vigorous": int(vigorous) if isinstance(vigorous, (int, float)) else None,
        "intensity_minutes_total": int(total) if isinstance(total, (int, float)) else None,
    }


def _extract_daily_stats_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload or not isinstance(payload, dict):
        return {}
    steps = _get_first_value(payload, ("totalSteps", "steps", "stepCount"))
    total_kcal = _get_first_value(payload, ("totalKilocalories", "totalCalories", "calories"))
    active_kcal = _get_first_value(payload, ("activeKilocalories", "activeCalories"))
    resting_hr = _get_first_value(payload, ("restingHeartRate", "restingHR"))
    return {
        "steps": int(steps) if isinstance(steps, (int, float)) else None,
        "calories_total_kcal": int(total_kcal) if isinstance(total_kcal, (int, float)) else None,
        "calories_active_kcal": int(active_kcal) if isinstance(active_kcal, (int, float)) else None,
        "resting_hr_bpm": int(resting_hr) if isinstance(resting_hr, (int, float)) else None,
    }


def _weight_entry_date(entry: dict[str, Any]) -> date | None:
    for key in ("date", "calendarDate", "measureDate", "dateTime", "samplePk"):
        value = entry.get(key)
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.split("T")[0])
            except ValueError:
                continue
    return None


def _weight_entry_kg(entry: dict[str, Any]) -> float | None:
    value = _get_first_value(entry, ("weight", "weightInKg", "weightInKilograms"))
    if isinstance(value, (int, float)):
        return float(value)
    value = _get_first_value(entry, ("weightInGrams", "weightInGram"))
    if isinstance(value, (int, float)):
        return float(value) / 1000
    return None


def _latest_weight_for_date(entries: list[dict[str, Any]], target: date) -> float | None:
    latest_weight: float | None = None
    for entry in entries:
        entry_date = _weight_entry_date(entry)
        if entry_date != target:
            continue
        weight_kg = _weight_entry_kg(entry)
        if weight_kg is not None:
            latest_weight = weight_kg
    return latest_weight


def _daily_links(date_str: str) -> dict[str, str]:
    return {
        "daily": f"/daily?date={date_str}&mode=normalized",
        "sleep": f"/sleep?date={date_str}&mode=normalized",
        "activities": f"/activities?start={date_str}&end={date_str}&mode=normalized",
        "activity_detail_template": "/activities/{activityId}?mode=normalized",
        "stress": f"/stress?date={date_str}&mode=normalized",
        "body_battery": f"/body-battery?date={date_str}&mode=normalized",
        "hrv": f"/hrv?date={date_str}&mode=normalized",
        "intensity_minutes": f"/intensity-minutes?date={date_str}&mode=normalized",
    }


def _normalize_daily(
    target_date: date,
    stats: dict[str, Any] | None,
    sleep: dict[str, Any] | None,
    stress: dict[str, Any] | None,
    body_battery: dict[str, Any] | None,
    hrv: dict[str, Any] | None,
    intensity: dict[str, Any] | None,
    weight_entries: list[dict[str, Any]],
    activities: list[dict[str, Any]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "steps": None,
        "calories_total_kcal": None,
        "calories_active_kcal": None,
        "resting_hr_bpm": None,
        "sleep_seconds": None,
        "sleep_score": None,
        "stress_avg": None,
        "body_battery_start": None,
        "body_battery_end": None,
        "hrv_status": None,
        "hrv_value": None,
        "intensity_minutes_moderate": None,
        "intensity_minutes_vigorous": None,
        "intensity_minutes_total": None,
        "weight_lb": None,
    }
    summary.update(_extract_daily_stats_fields(stats))
    summary.update(_extract_sleep_fields(sleep))
    summary.update(_extract_stress_fields(stress))
    summary.update(_extract_body_battery_fields(body_battery))
    summary.update(_extract_hrv_fields(hrv))
    summary.update(_extract_intensity_fields(intensity))

    weight_kg = _latest_weight_for_date(weight_entries, target_date)
    summary["weight_lb"] = (
        normalize.round_weight_lb(normalize.kg_to_lb(weight_kg)) if weight_kg is not None else None
    )

    date_str = target_date.isoformat()
    return {
        "date": date_str,
        "summary": summary,
        "activities": [_normalize_activity_stub(activity) for activity in activities],
        "links": _daily_links(date_str),
    }


def _daily_raw_payload(
    stats: dict[str, Any] | None,
    sleep: dict[str, Any] | None,
    stress: dict[str, Any] | None,
    body_battery: dict[str, Any] | None,
    hrv: dict[str, Any] | None,
    intensity: dict[str, Any] | None,
    weight_entries: list[dict[str, Any]],
    activities: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "stats": stats,
        "sleep": sleep,
        "stress": stress,
        "body_battery": body_battery,
        "hrv": hrv,
        "intensity_minutes": intensity,
        "weights": weight_entries,
        "activities": activities,
    }


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(message)s")

    app = FastAPI(dependencies=[Depends(api_key_guard)])
    register_exception_handlers(app)

    @app.middleware("http")
    async def request_logger(request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.cache_hit = False
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            payload = {
                "request_id": request_id,
                "endpoint": request.url.path,
                "params": dict(request.query_params),
                "latency_ms": latency_ms,
                "cache_hit": getattr(request.state, "cache_hit", False),
                "error_code": _error_code_from_exc(exc),
            }
            logger.error(json.dumps(payload, separators=(",", ":")))
            raise
        latency_ms = int((time.perf_counter() - start) * 1000)
        payload = {
            "request_id": request_id,
            "endpoint": request.url.path,
            "params": dict(request.query_params),
            "latency_ms": latency_ms,
            "cache_hit": getattr(request.state, "cache_hit", False),
            "error_code": None,
        }
        logger.info(json.dumps(payload, separators=(",", ":")))
        return response

    @app.get("/health")
    def health() -> dict[str, object]:
        settings = get_settings()
        client = get_garmin_client()
        token_last_refresh = client.token_last_refresh.isoformat() if client.token_last_refresh else None
        return {
            "status": "ok",
            "version": _resolve_version(),
            "auth": client.auth_status(),
            "token_dir": settings.token_dir,
            "token_last_refresh": token_last_refresh,
        }

    @app.get("/daily")
    def daily(
        request: Request,
        date: str = Query(..., pattern=DATE_PATTERN),
        mode: str = Query("normalized", pattern=MODE_PATTERN),
    ) -> dict[str, Any]:
        target_date = _parse_date(date, "date")
        params = {"date": date}
        cache_key = make_cache_key("daily", params, mode)
        cached = cache.get(cache_key)
        if cached is not None:
            request.state.cache_hit = True
            return cached

        client = get_garmin_client()
        client.ensure_auth_or_503()

        stats = client.get_daily_stats(target_date)
        sleep = client.get_sleep_summary(target_date)
        stress = client.get_stress_summary(target_date)
        body_battery = client.get_body_battery_summary(target_date)
        hrv = client.get_hrv_summary(target_date)
        intensity = client.get_intensity_minutes_summary(target_date)
        weight_entries = client.get_weight_range(target_date, target_date)
        activities = client.get_activities(target_date, target_date, None)

        if mode == "raw":
            payload = _daily_raw_payload(
                stats, sleep, stress, body_battery, hrv, intensity, weight_entries, activities
            )
        else:
            payload = _normalize_daily(
                target_date,
                stats,
                sleep,
                stress,
                body_battery,
                hrv,
                intensity,
                weight_entries,
                activities,
            )
        cache.set(cache_key, payload, settings.cache_ttl_seconds)
        return payload

    @app.get("/daily/range")
    def daily_range(
        request: Request,
        start: str = Query(..., pattern=DATE_PATTERN),
        end: str = Query(..., pattern=DATE_PATTERN),
        mode: str = Query("normalized", pattern=MODE_PATTERN),
    ) -> dict[str, Any]:
        _validate_range(start, end)
        start_date = _parse_date(start, "start")
        end_date = _parse_date(end, "end")
        params = {"start": start, "end": end}
        cache_key = make_cache_key("daily_range", params, mode)
        cached = cache.get(cache_key)
        if cached is not None:
            request.state.cache_hit = True
            return cached

        client = get_garmin_client()
        client.ensure_auth_or_503()

        days: list[dict[str, Any]] = []
        current = start_date
        while current <= end_date:
            stats = client.get_daily_stats(current)
            sleep = client.get_sleep_summary(current)
            stress = client.get_stress_summary(current)
            body_battery = client.get_body_battery_summary(current)
            hrv = client.get_hrv_summary(current)
            intensity = client.get_intensity_minutes_summary(current)
            weight_entries = client.get_weight_range(current, current)
            activities = client.get_activities(current, current, None)

            if mode == "raw":
                payload = _daily_raw_payload(
                    stats, sleep, stress, body_battery, hrv, intensity, weight_entries, activities
                )
                payload["date"] = current.isoformat()
                days.append(payload)
            else:
                days.append(
                    _normalize_daily(
                        current,
                        stats,
                        sleep,
                        stress,
                        body_battery,
                        hrv,
                        intensity,
                        weight_entries,
                        activities,
                    )
                )
            current += timedelta(days=1)

        response = {"start": start, "end": end, "days": days}
        cache.set(cache_key, response, settings.cache_ttl_seconds)
        return response

    @app.get("/sleep")
    def sleep(
        date: str = Query(..., pattern=DATE_PATTERN),
        mode: str = Query("normalized", pattern=MODE_PATTERN),
    ) -> None:
        _parse_date(date, "date")
        get_garmin_client().ensure_auth_or_503()
        _not_implemented()

    @app.get("/body")
    def body(
        start: str = Query(..., pattern=DATE_PATTERN),
        end: str = Query(..., pattern=DATE_PATTERN),
        mode: str = Query("normalized", pattern=MODE_PATTERN),
    ) -> None:
        _validate_range(start, end)
        get_garmin_client().ensure_auth_or_503()
        _not_implemented()

    @app.get("/activities")
    def activities(
        request: Request,
        start: str = Query(..., pattern=DATE_PATTERN),
        end: str = Query(..., pattern=DATE_PATTERN),
        type: str | None = Query(None),
        mode: str = Query("normalized", pattern=MODE_PATTERN),
    ) -> Any:
        _validate_range(start, end)
        start_date = _parse_date(start, "start")
        end_date = _parse_date(end, "end")
        params = {"start": start, "end": end, "type": type}
        cache_key = make_cache_key("activities", params, mode)
        cached = cache.get(cache_key)
        if cached is not None:
            request.state.cache_hit = True
            return cached

        client = get_garmin_client()
        client.ensure_auth_or_503()
        raw = client.get_activities(start_date, end_date, type)

        if mode == "raw":
            payload = raw
        else:
            payload = {
                "start": start,
                "end": end,
                "activities": [_normalize_activity_list_item(activity) for activity in raw],
            }
        cache.set(cache_key, payload, settings.cache_ttl_seconds)
        return payload

    @app.get("/activities/{activityId}")
    def activity_detail(
        request: Request,
        activityId: str = Path(...),
        mode: str = Query("normalized", pattern=MODE_PATTERN),
    ) -> Any:
        params = {"activityId": activityId}
        cache_key = make_cache_key("activity_detail", params, mode)
        cached = cache.get(cache_key)
        if cached is not None:
            request.state.cache_hit = True
            return cached

        client = get_garmin_client()
        client.ensure_auth_or_503()
        raw = client.get_activity_detail(activityId)
        if mode == "raw":
            payload = raw
        else:
            payload = _normalize_activity_detail(raw)
        cache.set(cache_key, payload, settings.cache_ttl_seconds)
        return payload

    @app.get("/stress")
    def stress(
        date: str = Query(..., pattern=DATE_PATTERN),
        mode: str = Query("normalized", pattern=MODE_PATTERN),
    ) -> None:
        _parse_date(date, "date")
        get_garmin_client().ensure_auth_or_503()
        _not_implemented()

    @app.get("/body-battery")
    def body_battery(
        date: str = Query(..., pattern=DATE_PATTERN),
        mode: str = Query("normalized", pattern=MODE_PATTERN),
    ) -> None:
        _parse_date(date, "date")
        get_garmin_client().ensure_auth_or_503()
        _not_implemented()

    @app.get("/hrv")
    def hrv(
        date: str = Query(..., pattern=DATE_PATTERN),
        mode: str = Query("normalized", pattern=MODE_PATTERN),
    ) -> None:
        _parse_date(date, "date")
        get_garmin_client().ensure_auth_or_503()
        _not_implemented()

    @app.get("/intensity-minutes")
    def intensity_minutes(
        date: str = Query(..., pattern=DATE_PATTERN),
        mode: str = Query("normalized", pattern=MODE_PATTERN),
    ) -> None:
        _parse_date(date, "date")
        get_garmin_client().ensure_auth_or_503()
        _not_implemented()

    return app


app = create_app()
