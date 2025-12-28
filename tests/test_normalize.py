from __future__ import annotations

from app import normalize


def test_conversions_constants() -> None:
    assert normalize.kg_to_lb(1.0) == normalize.LB_PER_KG
    assert normalize.m_to_yd(1.0) == normalize.YD_PER_M
    assert normalize.m_to_mi(1.0) == normalize.MI_PER_M
    assert normalize.m_to_ft(1.0) == normalize.FT_PER_M
    assert normalize.mps_to_mph(1.0) == normalize.MPH_PER_MPS


def test_rounding_rules() -> None:
    assert normalize.round_weight_lb(150.04) == 150.0
    assert normalize.round_weight_lb(150.06) == 150.1
    assert normalize.round_distance_mi(1.234) == 1.23
    assert normalize.round_distance_mi(1.235) == 1.24
    assert normalize.round_distance_yd(12.49) == 12
    assert normalize.round_distance_yd(12.51) == 13
    assert normalize.round_elevation_ft(100.49) == 100
    assert normalize.round_elevation_ft(100.51) == 101
    assert normalize.round_speed_mph(5.14) == 5.1
    assert normalize.round_speed_mph(5.16) == 5.2


def test_choose_distance_yd() -> None:
    meters = 100.0
    payload = normalize.choose_distance(meters)
    assert "distance_yd" in payload
    assert "distance_mi" not in payload
    assert payload["distance_yd"] == normalize.round_distance_yd(normalize.m_to_yd(meters))


def test_choose_distance_mi() -> None:
    meters = 1000.0
    payload = normalize.choose_distance(meters)
    assert "distance_mi" in payload
    assert "distance_yd" not in payload
    assert payload["distance_mi"] == normalize.round_distance_mi(normalize.m_to_mi(meters))


def test_distance_mi_always() -> None:
    meters = 100.0
    result = normalize.distance_mi_always(meters)
    assert result == normalize.round_distance_mi(normalize.m_to_mi(meters))
