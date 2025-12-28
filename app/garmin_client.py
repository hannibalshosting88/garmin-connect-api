from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any, Callable, TypeVar

from app.errors import GarminAuthFailure, MissingGarminAuth, UpstreamTimeout
from app.settings import get_settings

try:
    from garminconnect import Garmin  # type: ignore
except ImportError:  # pragma: no cover
    Garmin = None  # type: ignore[assignment]

try:
    from garminconnect import GarminConnectAuthenticationError  # type: ignore
except ImportError:  # pragma: no cover
    GarminConnectAuthenticationError = Exception  # type: ignore[assignment]

try:
    from garminconnect import GarminConnectConnectionError  # type: ignore
except ImportError:  # pragma: no cover
    GarminConnectConnectionError = Exception  # type: ignore[assignment]

try:
    from garminconnect import GarminConnectTimeoutError  # type: ignore
except ImportError:  # pragma: no cover
    GarminConnectTimeoutError = Exception  # type: ignore[assignment]

try:
    from garminconnect import GarminConnectTooManyRequestsError  # type: ignore
except ImportError:  # pragma: no cover
    GarminConnectTooManyRequestsError = Exception  # type: ignore[assignment]

TOKEN_FILE = "token.json"
META_FILE = "token_meta.json"
logger = logging.getLogger("garmin-service")
T = TypeVar("T")


@dataclass
class _TokenBundle:
    data: dict[str, Any]


class GarminClientWrapper:
    def __init__(self) -> None:
        settings = get_settings()
        self._token_dir = settings.token_dir
        self._email = settings.garmin_email
        self._password = settings.garmin_password
        self._auth_status: str = "needs_login"
        self.token_last_refresh: datetime | None = None
        self._tokens: _TokenBundle | None = None
        self._client: Garmin | None = None

        self._initialize_tokens()

    def auth_status(self) -> str:
        return self._auth_status

    def ensure_auth_or_503(self) -> None:
        if self._auth_status != "ok":
            raise MissingGarminAuth()

    def get_activities(self, start: date, end: date, activity_type: str | None) -> list[dict[str, Any]]:
        client = self._client_or_raise()
        data: list[dict[str, Any]] = []
        if not hasattr(client, "get_activities"):
            return []

        limit = 50
        max_pages = 20
        for page in range(max_pages):
            offset = page * limit
            batch = self._with_retries(lambda: client.get_activities(offset, limit))
            if not isinstance(batch, list) or not batch:
                break
            data.extend(batch)
            oldest = self._oldest_activity_date(batch)
            if oldest and oldest < start:
                break

        filtered = self._filter_activities_by_date(data, start, end)
        if activity_type:
            activity_type = activity_type.lower()
            filtered = [
                activity for activity in filtered if self._activity_type(activity).lower() == activity_type
            ]
        return filtered

    def get_activity_detail(self, activity_id: str) -> dict[str, Any]:
        client = self._client_or_raise()
        if hasattr(client, "get_activity_details"):
            return self._with_retries(lambda: client.get_activity_details(activity_id))
        if hasattr(client, "get_activity_detail"):
            return self._with_retries(lambda: client.get_activity_detail(activity_id))
        raise RuntimeError("Activity detail endpoint is unavailable")

    def get_daily_stats(self, target_date: date) -> dict[str, Any] | None:
        client = self._client_or_raise()
        date_str = target_date.isoformat()
        if hasattr(client, "get_stats"):
            return self._with_retries(lambda: client.get_stats(date_str))
        if hasattr(client, "get_daily_summary"):
            return self._with_retries(lambda: client.get_daily_summary(date_str))
        if hasattr(client, "get_steps_data"):
            return self._with_retries(lambda: client.get_steps_data(date_str))
        return None

    def get_sleep_summary(self, target_date: date) -> dict[str, Any] | None:
        client = self._client_or_raise()
        date_str = target_date.isoformat()
        if hasattr(client, "get_sleep_data"):
            return self._with_retries(lambda: client.get_sleep_data(date_str))
        return None

    def get_stress_summary(self, target_date: date) -> dict[str, Any] | None:
        client = self._client_or_raise()
        date_str = target_date.isoformat()
        if hasattr(client, "get_stress_data"):
            return self._with_retries(lambda: client.get_stress_data(date_str))
        return None

    def get_body_battery_summary(self, target_date: date) -> dict[str, Any] | None:
        client = self._client_or_raise()
        date_str = target_date.isoformat()
        if hasattr(client, "get_body_battery"):
            return self._with_retries(lambda: client.get_body_battery(date_str))
        return None

    def get_hrv_summary(self, target_date: date) -> dict[str, Any] | None:
        client = self._client_or_raise()
        date_str = target_date.isoformat()
        if hasattr(client, "get_hrv_data"):
            return self._with_retries(lambda: client.get_hrv_data(date_str))
        return None

    def get_intensity_minutes_summary(self, target_date: date) -> dict[str, Any] | None:
        client = self._client_or_raise()
        date_str = target_date.isoformat()
        if hasattr(client, "get_intensity_minutes"):
            return self._with_retries(lambda: client.get_intensity_minutes(date_str))
        return None

    def get_weight_range(self, start: date, end: date) -> list[dict[str, Any]]:
        client = self._client_or_raise()
        start_str = start.isoformat()
        end_str = end.isoformat()
        if hasattr(client, "get_weight_data"):
            data = self._with_retries(lambda: client.get_weight_data(start_str, end_str))
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("weightSamples", [])
        return []

    def _initialize_tokens(self) -> None:
        tokens = self._load_tokens()
        if tokens is not None:
            try:
                self._with_retries(lambda: self._login_with_tokens(tokens.data))
                self._with_retries(self._refresh_tokens)
                self._auth_status = "ok"
                return
            except (GarminAuthFailure, UpstreamTimeout) as exc:
                logger.exception(
                    "garmin_refresh_failed",
                    extra={
                        "token_dir": self._token_dir,
                        "has_email": bool(self._email),
                        "error": str(exc),
                    },
                )
                self._auth_status = "error"
                if self._email and self._password:
                    self._try_relogin_with_creds()
                return
            except Exception as exc:
                logger.exception(
                    "garmin_refresh_failed",
                    extra={
                        "token_dir": self._token_dir,
                        "has_email": bool(self._email),
                        "error": str(exc),
                    },
                )
                self._auth_status = "error"
                if self._email and self._password:
                    self._try_relogin_with_creds()
                return

        if self._email and self._password:
            self._try_relogin_with_creds()
        else:
            self._auth_status = "needs_login"

    def _load_tokens(self) -> _TokenBundle | None:
        token_path = os.path.join(self._token_dir, TOKEN_FILE)
        if not os.path.isfile(token_path):
            return None
        try:
            with open(token_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.exception(
                "garmin_tokens_load_failed",
                extra={
                    "token_dir": self._token_dir,
                    "has_email": bool(self._email),
                    "error": str(exc),
                },
            )
            return None
        self._tokens = _TokenBundle(data=data)
        self.token_last_refresh = self._load_meta()
        return self._tokens

    def _load_meta(self) -> datetime | None:
        meta_path = os.path.join(self._token_dir, META_FILE)
        if not os.path.isfile(meta_path):
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.exception(
                "garmin_tokens_meta_load_failed",
                extra={
                    "token_dir": self._token_dir,
                    "has_email": bool(self._email),
                    "error": str(exc),
                },
            )
            return None
        value = payload.get("last_refresh")
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _login(self) -> None:
        if not self._email or not self._password:
            raise GarminAuthFailure("Missing Garmin credentials")
        if Garmin is None:
            raise RuntimeError("Garmin client library is unavailable")
        self._client = Garmin(self._email, self._password)
        self._client.login()
        self.token_last_refresh = datetime.now(timezone.utc)
        self._persist_tokens_from_client()

    def _login_with_tokens(self, tokens: dict[str, Any]) -> None:
        if Garmin is None:
            raise RuntimeError("Garmin client library is unavailable")
        self._client = Garmin(self._email or "", self._password or "")
        garth = getattr(self._client, "garth", None)
        restored = False
        if garth is not None:
            if hasattr(garth, "restore"):
                garth.restore(tokens)
                restored = True
            elif hasattr(garth, "loads"):
                garth.loads(json.dumps(tokens))
                restored = True
            elif hasattr(garth, "load") and isinstance(tokens, (str, bytes, os.PathLike)):
                garth.load(tokens)
                restored = True
        if not restored:
            self._login()
            return
        if garth is not None and hasattr(garth, "refresh"):
            garth.refresh()
        self.token_last_refresh = datetime.now(timezone.utc)
        self._persist_tokens_from_client()

    def _refresh_tokens(self) -> None:
        if not self._client:
            raise GarminAuthFailure("Missing Garmin client")
        garth = getattr(self._client, "garth", None)
        if garth is not None and hasattr(garth, "refresh"):
            garth.refresh()
        self.token_last_refresh = datetime.now(timezone.utc)
        self._persist_tokens_from_client()

    def _persist_tokens(self) -> None:
        self._ensure_token_dir()
        token_path = os.path.join(self._token_dir, TOKEN_FILE)
        payload = self._tokens.data if self._tokens else {}
        try:
            self._atomic_write_json(token_path, payload)
            self._persist_meta()
        except OSError as exc:
            logger.exception(
                "garmin_tokens_write_failed",
                extra={
                    "token_dir": self._token_dir,
                    "has_email": bool(self._email),
                    "error": str(exc),
                },
            )
            raise

    def _persist_tokens_from_client(self) -> None:
        if not self._client:
            raise GarminAuthFailure("Missing Garmin client")
        garth = getattr(self._client, "garth", None)
        data: dict[str, Any] | None = None
        if garth is not None:
            if hasattr(garth, "dumps"):
                dumped = garth.dumps()
                if isinstance(dumped, str):
                    try:
                        data = json.loads(dumped)
                    except json.JSONDecodeError:
                        data = {"raw": dumped}
                elif isinstance(dumped, dict):
                    data = dumped
            elif hasattr(garth, "dump"):
                dumped = garth.dump()
                if isinstance(dumped, dict):
                    data = dumped
        if data is None:
            data = self._tokens.data if self._tokens else {}
        self._tokens = _TokenBundle(data=data)
        self._persist_tokens()

    def _persist_meta(self) -> None:
        self._ensure_token_dir()
        meta_path = os.path.join(self._token_dir, META_FILE)
        last_refresh = self.token_last_refresh or datetime.now(timezone.utc)
        payload = {"last_refresh": last_refresh.isoformat()}
        try:
            self._atomic_write_json(meta_path, payload)
        except OSError as exc:
            logger.exception(
                "garmin_tokens_meta_write_failed",
                extra={
                    "token_dir": self._token_dir,
                    "has_email": bool(self._email),
                    "error": str(exc),
                },
            )
            raise

    def _ensure_token_dir(self) -> None:
        os.makedirs(self._token_dir, mode=0o700, exist_ok=True)
        try:
            os.chmod(self._token_dir, 0o700)
        except OSError:
            pass

    def _atomic_write_json(self, path: str, payload: dict[str, Any]) -> None:
        directory = os.path.dirname(path)
        base = os.path.basename(path)
        temp_path = os.path.join(directory, f".{base}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(temp_path, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
        os.replace(temp_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _with_retries(self, func: Callable[[], T]) -> T:
        attempts = 3
        base_delay = 0.5
        for attempt in range(1, attempts + 1):
            try:
                return func()
            except GarminConnectAuthenticationError as exc:
                raise GarminAuthFailure(str(exc)) from exc
            except GarminConnectTimeoutError as exc:
                last_exc: Exception = UpstreamTimeout(str(exc))
            except GarminConnectConnectionError as exc:
                last_exc = UpstreamTimeout(str(exc))
            except GarminConnectTooManyRequestsError as exc:
                last_exc = UpstreamTimeout(str(exc))
            except GarminAuthFailure:
                raise
            except TimeoutError as exc:
                last_exc: Exception = UpstreamTimeout(str(exc))
            except Exception as exc:  # pragma: no cover - placeholder for upstream handling
                last_exc = exc
            if attempt < attempts:
                delay = base_delay * (2 ** (attempt - 1))
                delay += random.uniform(0, 0.2)
                time.sleep(delay)
            else:
                raise last_exc

    def _client_or_raise(self) -> Garmin:
        if not self._client:
            raise MissingGarminAuth()
        return self._client

    def _try_relogin_with_creds(self) -> None:
        try:
            self._with_retries(self._login)
            self._auth_status = "ok"
        except (GarminAuthFailure, UpstreamTimeout) as exc:
            logger.exception(
                "garmin_login_failed",
                extra={
                    "token_dir": self._token_dir,
                    "has_email": bool(self._email),
                    "error": str(exc),
                },
            )
            self._auth_status = "error"
        except Exception as exc:
            logger.exception(
                "garmin_login_failed",
                extra={
                    "token_dir": self._token_dir,
                    "has_email": bool(self._email),
                    "error": str(exc),
                },
            )
            self._auth_status = "error"

    @staticmethod
    def _activity_type(activity: dict[str, Any]) -> str:
        activity_type = activity.get("activityType") or {}
        if isinstance(activity_type, dict):
            return (
                activity_type.get("typeKey")
                or activity_type.get("type")
                or activity_type.get("typeName")
                or ""
            )
        if isinstance(activity_type, str):
            return activity_type
        return activity.get("type") or ""

    @classmethod
    def _filter_activities_by_date(
        cls, activities: list[dict[str, Any]], start: date, end: date
    ) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for activity in activities:
            activity_date = cls._activity_date(activity)
            if not activity_date:
                continue
            if start <= activity_date <= end:
                filtered.append(activity)
        return filtered

    @staticmethod
    def _activity_date(activity: dict[str, Any]) -> date | None:
        for key in ("startTimeLocal", "startTimeGMT", "startTime", "startTimeUtc"):
            value = activity.get(key)
            if isinstance(value, str):
                try:
                    return date.fromisoformat(value.split(" ")[0])
                except ValueError:
                    continue
        timestamp = activity.get("beginTimestamp")
        if isinstance(timestamp, (int, float)):
            try:
                return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date()
            except ValueError:
                return None
        return None

    @classmethod
    def _oldest_activity_date(cls, activities: list[dict[str, Any]]) -> date | None:
        dates = [cls._activity_date(activity) for activity in activities]
        valid = [value for value in dates if value is not None]
        return min(valid) if valid else None


@lru_cache(maxsize=1)
def get_garmin_client() -> GarminClientWrapper:
    return GarminClientWrapper()
