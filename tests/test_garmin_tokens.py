from __future__ import annotations

from typing import Any

import pytest

import app.garmin_client as gc


class _GarthLoadOnly:
    def __init__(self) -> None:
        self.load_called = False

    def load(self, _: Any) -> None:
        self.load_called = True


class _GarthRestore:
    def __init__(self) -> None:
        self.restore_called = False

    def restore(self, _: dict[str, Any]) -> None:
        self.restore_called = True


class _StubGarmin:
    def __init__(self, _: str, __: str) -> None:
        self.garth = _GarthLoadOnly()


class _StubGarminRestore:
    def __init__(self, _: str, __: str) -> None:
        self.garth = _GarthRestore()


def test_login_with_tokens_load_only_falls_back_to_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gc, "Garmin", _StubGarmin)
    client = gc.GarminClientWrapper.__new__(gc.GarminClientWrapper)
    client._email = "user@example.com"
    client._password = "pass"

    login_called = {"value": False}

    def _fake_login(self: gc.GarminClientWrapper) -> None:
        login_called["value"] = True

    monkeypatch.setattr(gc.GarminClientWrapper, "_login", _fake_login)
    client._login_with_tokens({"access_token": "stub"})

    assert login_called["value"] is True
    assert client._client.garth.load_called is False


def test_login_with_tokens_restore_uses_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gc, "Garmin", _StubGarminRestore)
    client = gc.GarminClientWrapper.__new__(gc.GarminClientWrapper)
    client._email = "user@example.com"
    client._password = "pass"

    login_called = {"value": False}

    def _fake_login(self: gc.GarminClientWrapper) -> None:
        login_called["value"] = True

    monkeypatch.setattr(gc.GarminClientWrapper, "_login", _fake_login)
    client._persist_tokens_from_client = lambda: None  # type: ignore[assignment]
    client._login_with_tokens({"access_token": "stub"})

    assert login_called["value"] is False
    assert client._client.garth.restore_called is True
