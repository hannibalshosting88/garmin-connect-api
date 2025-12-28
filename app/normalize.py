from __future__ import annotations

LB_PER_KG = 2.2046226218
YD_PER_M = 1.0936132983
MI_PER_M = 0.000621371192
FT_PER_M = 3.280839895
MPH_PER_MPS = 2.2369362921


def kg_to_lb(kg: float) -> float:
    return kg * LB_PER_KG


def m_to_yd(meters: float) -> float:
    return meters * YD_PER_M


def m_to_mi(meters: float) -> float:
    return meters * MI_PER_M


def m_to_ft(meters: float) -> float:
    return meters * FT_PER_M


def mps_to_mph(mps: float) -> float:
    return mps * MPH_PER_MPS


def round_weight_lb(value: float) -> float:
    return round(value, 1)


def round_distance_mi(value: float) -> float:
    return round(value, 2)


def round_distance_yd(value: float) -> int:
    return int(round(value))


def round_elevation_ft(value: float) -> int:
    return int(round(value))


def round_speed_mph(value: float) -> float:
    return round(value, 1)


def distance_mi_always(distance_meters: float) -> float:
    return round_distance_mi(m_to_mi(distance_meters))


def choose_distance(distance_meters: float) -> dict[str, float | int]:
    distance_mi = m_to_mi(distance_meters)
    if distance_mi < 0.25:
        return {"distance_yd": round_distance_yd(m_to_yd(distance_meters))}
    return {"distance_mi": round_distance_mi(distance_mi)}
