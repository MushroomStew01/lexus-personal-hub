from __future__ import annotations

"""Telemetry-based Lexus readiness score for the owner's private dashboard."""

import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import Snapshot, Trip
from .storage import primary_vehicle
from .timeutil import utcnow

_TIRE_KEYS = {
    "front_driver_tire": "Front driver tire",
    "front_passenger_tire": "Front passenger tire",
    "rear_driver_tire": "Rear driver tire",
    "rear_passenger_tire": "Rear passenger tire",
}
_OPENING_KEYS = {
    "front_driver_door": "Front driver door",
    "front_passenger_door": "Front passenger door",
    "rear_driver_door": "Rear driver door",
    "rear_passenger_door": "Rear passenger door",
    "front_driver_window": "Front driver window",
    "front_passenger_window": "Front passenger window",
    "rear_driver_window": "Rear driver window",
    "rear_passenger_window": "Rear passenger window",
    "moonroof": "Moonroof",
    "hood": "Hood",
    "trunk": "Trunk",
}
_LOCK_KEYS = {
    "front_driver_door_lock": "Front driver door",
    "front_passenger_door_lock": "Front passenger door",
    "rear_driver_door_lock": "Rear driver door",
    "rear_passenger_door_lock": "Rear passenger door",
    "trunk_door_lock": "Trunk",
}


def _snapshot_status(snapshot: Snapshot | None) -> dict[str, object]:
    if snapshot is None or not snapshot.raw_json:
        return {}
    try:
        payload = json.loads(snapshot.raw_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    status = payload.get("status") if isinstance(payload, dict) else None
    return status if isinstance(status, dict) else {}


def _record_value(status: dict[str, object], key: str) -> object:
    record = status.get(key)
    if not isinstance(record, dict):
        return None
    return record.get("value")


def _record_text(status: dict[str, object], key: str) -> str:
    value = _record_value(status, key)
    return str(value or "").strip().lower()


def _record_number(status: dict[str, object], key: str) -> float | None:
    value = _record_value(status, key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _check(
    name: str,
    state: str,
    detail: str,
    deduction: int = 0,
) -> dict[str, object]:
    return {
        "name": name,
        "state": state,
        "detail": detail,
        "deduction": deduction,
    }


def _grade(score: int) -> tuple[str, str]:
    if score >= 90:
        return "Excellent", "good"
    if score >= 75:
        return "Good", "good"
    if score >= 60:
        return "Attention", "warn"
    return "Needs attention", "alert"


def vehicle_health_score(session: Session, settings: Settings) -> dict[str, object]:
    """Return a readiness score based only on telemetry the app can actually observe.

    This is intentionally not a mechanical diagnostic score. It summarizes connectivity,
    tires, parked security, fuel/range, and service-due information.
    """

    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return {
            "ready": False,
            "score": None,
            "grade": "Waiting for telemetry",
            "grade_state": "unknown",
            "checks": [],
        }

    latest = session.scalar(
        select(Snapshot)
        .where(Snapshot.vehicle_id == vehicle.id)
        .order_by(Snapshot.observed_at.desc())
        .limit(1)
    )
    if latest is None:
        return {
            "ready": False,
            "score": None,
            "grade": "Waiting for telemetry",
            "grade_state": "unknown",
            "checks": [],
        }

    status = _snapshot_status(latest)
    checks: list[dict[str, object]] = []
    deduction = 0

    # Connectivity / freshness.
    if latest.source_updated_at is None:
        freshness_deduction = 4
        checks.append(_check("Connectivity", "unknown", "Source update time unavailable", 4))
    else:
        age = max(timedelta(0), utcnow() - latest.source_updated_at)
        stale_after = timedelta(minutes=settings.stale_telemetry_minutes)
        if age >= stale_after:
            freshness_deduction = 12
            checks.append(
                _check(
                    "Connectivity",
                    "alert",
                    f"Telemetry is {age.total_seconds() / 3600:.1f} hours old",
                    12,
                )
            )
        else:
            freshness_deduction = 0
            checks.append(
                _check(
                    "Connectivity",
                    "ok",
                    f"Updated {age.total_seconds() / 60:.0f} minutes ago",
                )
            )
    deduction += freshness_deduction

    # Tire pressures. Missing sensors do not count against the vehicle.
    low_tires: list[str] = []
    critical_tires: list[str] = []
    available_tires = 0
    for key, label in _TIRE_KEYS.items():
        pressure = _record_number(status, key)
        if pressure is None:
            continue
        available_tires += 1
        if pressure < max(0.0, settings.low_tire_psi - 5):
            critical_tires.append(f"{label} {pressure:.0f} psi")
        elif pressure < settings.low_tire_psi:
            low_tires.append(f"{label} {pressure:.0f} psi")
    tire_deduction = min(24, len(low_tires) * 6 + len(critical_tires) * 12)
    deduction += tire_deduction
    if critical_tires:
        checks.append(_check("Tires", "alert", "; ".join(critical_tires + low_tires), tire_deduction))
    elif low_tires:
        checks.append(_check("Tires", "warn", "; ".join(low_tires), tire_deduction))
    elif available_tires:
        checks.append(_check("Tires", "ok", f"All {available_tires} reported tires are above threshold"))
    else:
        checks.append(_check("Tires", "unknown", "No tire pressure telemetry"))

    # Security is only scored while parked so intentional open windows while driving do not hurt it.
    open_trip = session.scalar(
        select(Trip.id)
        .where(Trip.vehicle_id == vehicle.id, Trip.is_open.is_(True))
        .limit(1)
    )
    parked = (
        open_trip is None
        and (latest.speed_kph is None or latest.speed_kph <= settings.parking_speed_threshold_kph)
    )
    if parked:
        open_items = [label for key, label in _OPENING_KEYS.items() if _record_text(status, key) == "open"]
        unlocked_items = [
            label for key, label in _LOCK_KEYS.items() if _record_text(status, key) == "unlocked"
        ]
        security_deduction = min(24, len(open_items) * 5 + len(unlocked_items) * 3)
        deduction += security_deduction
        if open_items:
            detail = "Open: " + ", ".join(open_items)
            if unlocked_items:
                detail += " · Unlocked: " + ", ".join(unlocked_items)
            checks.append(_check("Parked security", "alert", detail, security_deduction))
        elif unlocked_items:
            checks.append(
                _check(
                    "Parked security",
                    "warn",
                    "Unlocked: " + ", ".join(unlocked_items),
                    security_deduction,
                )
            )
        else:
            checks.append(_check("Parked security", "ok", "Reported openings closed and locks secured"))
    else:
        checks.append(_check("Parked security", "ok", "Vehicle appears to be in use"))

    # Fuel and range are one combined readiness check to avoid double-penalizing the same condition.
    fuel_percent = latest.fuel_percent
    range_km = latest.range_km
    fuel_deduction = 0
    fuel_state = "ok"
    fuel_detail = "Fuel and range are above warning thresholds"
    if (fuel_percent is not None and fuel_percent <= 10) or (range_km is not None and range_km <= 40):
        fuel_deduction = 12
        fuel_state = "alert"
    elif (
        fuel_percent is not None
        and fuel_percent <= settings.low_fuel_percent
        or range_km is not None
        and range_km <= settings.low_range_km
    ):
        fuel_deduction = 6
        fuel_state = "warn"
    if fuel_deduction:
        pieces = []
        if fuel_percent is not None:
            pieces.append(f"Fuel {fuel_percent:.0f}%")
        if range_km is not None:
            pieces.append(f"Range {range_km:.0f} km")
        fuel_detail = " · ".join(pieces)
    deduction += fuel_deduction
    checks.append(_check("Fuel & range", fuel_state, fuel_detail, fuel_deduction))

    # Prefer configured service interval, with the Toyota next-service sensor as a fallback.
    service_remaining: float | None = None
    if settings.last_service_odometer_km is not None and latest.odometer_km is not None:
        service_remaining = (
            settings.last_service_odometer_km
            + settings.service_interval_km
            - latest.odometer_km
        )
    if service_remaining is None:
        service_remaining = _record_number(status, "next_service")

    service_deduction = 0
    if service_remaining is None:
        checks.append(_check("Maintenance", "unknown", "No service-due distance available"))
    elif service_remaining <= 0:
        service_deduction = 15
        checks.append(
            _check(
                "Maintenance",
                "alert",
                f"Service overdue by {abs(service_remaining):.0f} km",
                service_deduction,
            )
        )
    elif service_remaining <= 800:
        service_deduction = 6
        checks.append(
            _check(
                "Maintenance",
                "warn",
                f"Service due in about {service_remaining:.0f} km",
                service_deduction,
            )
        )
    else:
        checks.append(_check("Maintenance", "ok", f"Service due in about {service_remaining:.0f} km"))
    deduction += service_deduction

    score = max(0, min(100, 100 - deduction))
    grade, grade_state = _grade(score)
    attention_count = sum(1 for item in checks if item["state"] in {"warn", "alert"})
    return {
        "ready": True,
        "score": score,
        "grade": grade,
        "grade_state": grade_state,
        "attention_count": attention_count,
        "parked": parked,
        "checks": checks,
        "disclaimer": "Telemetry readiness score; not a mechanical diagnosis.",
    }
