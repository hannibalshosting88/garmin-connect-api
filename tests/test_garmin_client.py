from __future__ import annotations

from datetime import date
from typing import Any

from app.garmin_client import GarminClientWrapper


class _StubClient:
    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self._pages = pages

    def get_activities(self, offset: int, limit: int) -> list[dict[str, Any]]:
        index = offset // limit
        if index >= len(self._pages):
            return []
        return self._pages[index]


def test_get_activities_pages_and_filters_by_date() -> None:
    pages = [
        [
            {"activityId": 1, "startTimeLocal": "2025-12-27 10:00:00", "activityType": "running"},
            {"activityId": 2, "startTimeLocal": "2025-12-26 10:00:00", "activityType": "running"},
        ],
        [
            {"activityId": 3, "startTimeLocal": "2025-12-19 10:00:00", "activityType": "running"},
        ],
    ]
    client = GarminClientWrapper.__new__(GarminClientWrapper)
    client._client = _StubClient(pages)  # type: ignore[attr-defined]

    result = client.get_activities(date(2025, 12, 20), date(2025, 12, 27), None)

    ids = [activity["activityId"] for activity in result]
    assert ids == [1, 2]
