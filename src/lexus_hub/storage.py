from __future__ import annotations

"""Local persistence for the account owner's own vehicle telemetry."""

import json
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import FuelFill, Snapshot, Trip, TripPoint, Vehicle
from .providers.base import VehicleReading
from .timeutil import as_utc_naive, utcnow


def primary_vehicle(session: Session, settings: Settings) -> Vehicle | None:
    provider_id = "ha:primary" if settings.provider == "home_assistant" else "mock:primary"
    return session.scalar(
        select(Vehicle).where(Vehicle.provider_vehicle_id == provider_id).limit(1)
    )


def _snapshot_has_location(snapshot: Snapshot | None) -> bool:
    return bool(
        snapshot is not None
        and snapshot.latitude is not None
        and snapshot.longitude is not None
    )


def _haversine_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    earth_radius_m = 6_371_000.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    return earth_radius_m * 2 * asin(min(1.0, sqrt(a)))


def _gps_distance_m(previous: Snapshot | None, current: Snapshot | None) -> float | None:
    if not _snapshot_has_location(previous) or not _snapshot_has_location(current):
        return None
    assert previous is not None and current is not None
    return _haversine_m(
        float(previous.latitude),
        float(previous.longitude),
        float(current.latitude),
        float(current.longitude),
    )


def _movement_signals(
    previous: Snapshot | None,
    current: Snapshot,
    settings: Settings,
) -> dict[str, object]:
    odometer_delta_km: float | None = None
    if (
        previous is not None
        and previous.odometer_km is not None
        and current.odometer_km is not None
    ):
        odometer_delta_km = current.odometer_km - previous.odometer_km

    gps_distance_m = _gps_distance_m(previous, current)
    gps_threshold_m = max(100.0, settings.min_trip_delta_km * 1000.0)
    speed_threshold_kph = max(3.0, settings.parking_speed_threshold_kph + 1.0)

    odometer_moving = bool(
        odometer_delta_km is not None
        and odometer_delta_km >= settings.min_trip_delta_km
    )
    speed_moving = bool(
        current.speed_kph is not None and current.speed_kph >= speed_threshold_kph
    )
    gps_moving = bool(
        gps_distance_m is not None and gps_distance_m >= gps_threshold_m
    )

    return {
        "moving": odometer_moving or speed_moving or gps_moving,
        "odometer_moving": odometer_moving,
        "speed_moving": speed_moving,
        "gps_moving": gps_moving,
        "odometer_delta_km": odometer_delta_km,
        "gps_distance_m": gps_distance_m,
        "gps_threshold_m": gps_threshold_m,
        "speed_threshold_kph": speed_threshold_kph,
    }


def _add_trip_point(session: Session, trip: Trip, snapshot: Snapshot | None) -> None:
    if not _snapshot_has_location(snapshot) or snapshot is None:
        return
    last_point = session.scalar(
        select(TripPoint)
        .where(TripPoint.trip_id == trip.id)
        .order_by(TripPoint.observed_at.desc())
        .limit(1)
    )
    if last_point is not None:
        same_time = last_point.observed_at == snapshot.observed_at
        same_place = (
            abs(last_point.latitude - float(snapshot.latitude)) < 0.000001
            and abs(last_point.longitude - float(snapshot.longitude)) < 0.000001
        )
        if same_time or same_place:
            return
    session.add(
        TripPoint(
            trip_id=trip.id,
            observed_at=snapshot.observed_at,
            latitude=float(snapshot.latitude),
            longitude=float(snapshot.longitude),
            odometer_km=snapshot.odometer_km,
        )
    )


def _close_trip_for_gap(open_trip: Trip | None) -> None:
    if open_trip is not None:
        open_trip.ended_at = open_trip.last_movement_at
        open_trip.is_open = False


def _reconcile_delayed_odometer(
    session: Session,
    current: Snapshot,
    settings: Settings,
    signals: dict[str, object],
) -> bool:
    """Apply a late odometer jump to a recent GPS/speed trip instead of creating a duplicate.

    Toyota Connected Services can update parked location/speed before odometer data catches up.
    We only reconcile a completed trip that still has essentially zero odometer distance and whose
    end position is still near the car's current position. This keeps odometer distance authoritative
    without turning a delayed cloud refresh into a second phantom trip.
    """

    if not signals.get("odometer_moving"):
        return False
    if signals.get("speed_moving") or signals.get("gps_moving"):
        return False
    if current.odometer_km is None or not _snapshot_has_location(current):
        return False

    cutoff = current.observed_at - timedelta(hours=settings.max_snapshot_gap_hours)
    recent = session.scalar(
        select(Trip)
        .where(
            Trip.vehicle_id == current.vehicle_id,
            Trip.is_open.is_(False),
            Trip.ended_at.is_not(None),
            Trip.ended_at >= cutoff,
            Trip.distance_km < settings.min_trip_delta_km,
        )
        .order_by(Trip.ended_at.desc())
        .limit(1)
    )
    if (
        recent is None
        or recent.end_latitude is None
        or recent.end_longitude is None
    ):
        return False

    distance_from_trip_end_m = _haversine_m(
        float(recent.end_latitude),
        float(recent.end_longitude),
        float(current.latitude),
        float(current.longitude),
    )
    allowed_m = max(500.0, float(signals["gps_threshold_m"]) * 2.0)
    if distance_from_trip_end_m > allowed_m:
        return False

    if current.odometer_km <= recent.start_odometer_km:
        return False

    recent.end_odometer_km = current.odometer_km
    recent.distance_km = max(0.0, current.odometer_km - recent.start_odometer_km)
    return True


def _update_trip(
    session: Session,
    previous: Snapshot | None,
    current: Snapshot,
    settings: Settings,
) -> None:
    open_trip = session.scalar(
        select(Trip)
        .where(Trip.vehicle_id == current.vehicle_id, Trip.is_open.is_(True))
        .order_by(Trip.started_at.desc())
        .limit(1)
    )
    if previous is None:
        return

    gap = current.observed_at - previous.observed_at
    if gap < timedelta(0) or gap > timedelta(hours=settings.max_snapshot_gap_hours):
        _close_trip_for_gap(open_trip)
        return

    signals = _movement_signals(previous, current, settings)
    odometer_delta = signals["odometer_delta_km"]
    if isinstance(odometer_delta, (int, float)) and odometer_delta < -0.01:
        return

    if open_trip is None:
        if not signals["moving"]:
            return
        if _reconcile_delayed_odometer(session, current, settings, signals):
            return

        baseline_odometer = (
            previous.odometer_km
            if previous.odometer_km is not None
            else current.odometer_km
        )
        if baseline_odometer is None:
            return
        end_odometer = current.odometer_km if current.odometer_km is not None else baseline_odometer
        trip = Trip(
            vehicle_id=current.vehicle_id,
            started_at=previous.observed_at,
            ended_at=None,
            last_movement_at=current.observed_at,
            start_odometer_km=baseline_odometer,
            end_odometer_km=end_odometer,
            distance_km=max(0.0, end_odometer - baseline_odometer),
            start_latitude=previous.latitude,
            start_longitude=previous.longitude,
            end_latitude=current.latitude,
            end_longitude=current.longitude,
            is_open=True,
        )
        session.add(trip)
        session.flush()
        _add_trip_point(session, trip, previous)
        _add_trip_point(session, trip, current)
        return

    if open_trip.start_latitude is None and _snapshot_has_location(previous):
        open_trip.start_latitude = previous.latitude
        open_trip.start_longitude = previous.longitude
        _add_trip_point(session, open_trip, previous)

    if _snapshot_has_location(current):
        open_trip.end_latitude = current.latitude
        open_trip.end_longitude = current.longitude
        _add_trip_point(session, open_trip, current)

    if (
        current.odometer_km is not None
        and current.odometer_km > open_trip.end_odometer_km + 0.01
    ):
        open_trip.end_odometer_km = current.odometer_km
        open_trip.distance_km = max(
            0.0,
            current.odometer_km - open_trip.start_odometer_km,
        )

    if signals["moving"]:
        open_trip.last_movement_at = current.observed_at
        return

    idle = current.observed_at - open_trip.last_movement_at
    if idle >= timedelta(minutes=settings.trip_idle_close_minutes):
        open_trip.ended_at = open_trip.last_movement_at
        open_trip.is_open = False


def trip_diagnostics(session: Session, settings: Settings) -> dict[str, object]:
    """Explain the latest trip-detection decision without exposing exact GPS coordinates."""

    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return {"ready": False, "reason": "No vehicle has been saved yet."}

    snapshots = session.scalars(
        select(Snapshot)
        .where(Snapshot.vehicle_id == vehicle.id)
        .order_by(Snapshot.observed_at.desc())
        .limit(2)
    ).all()
    if not snapshots:
        return {"ready": False, "reason": "No snapshots have been saved yet."}

    current = snapshots[0]
    previous = snapshots[1] if len(snapshots) > 1 else None
    signals = _movement_signals(previous, current, settings)
    open_trip = session.scalar(
        select(Trip)
        .where(Trip.vehicle_id == vehicle.id, Trip.is_open.is_(True))
        .order_by(Trip.started_at.desc())
        .limit(1)
    )
    latest_trip = session.scalar(
        select(Trip)
        .where(Trip.vehicle_id == vehicle.id)
        .order_by(Trip.started_at.desc())
        .limit(1)
    )

    source_age_minutes = None
    if current.source_updated_at is not None:
        source_age_minutes = max(
            0.0,
            (utcnow() - current.source_updated_at).total_seconds() / 60.0,
        )

    if previous is None:
        decision = "Need another snapshot before movement can be compared."
    elif open_trip is not None:
        decision = (
            "Trip is open; movement signals keep it active until the configured idle timeout."
            if signals["moving"]
            else "Trip is open but no movement signal is present; waiting for the idle timeout."
        )
    elif signals["moving"]:
        decision = "Latest snapshot pair contains a movement signal and can start a trip."
    else:
        decision = "No movement signal in the latest snapshot pair."

    return {
        "ready": True,
        "vehicle": vehicle.display_name,
        "current_snapshot": {
            "observed_at": current.observed_at.isoformat(),
            "source_updated_at": (
                current.source_updated_at.isoformat() if current.source_updated_at else None
            ),
            "source_age_minutes": (
                round(source_age_minutes, 1) if source_age_minutes is not None else None
            ),
            "odometer_km": current.odometer_km,
            "speed_kph": current.speed_kph,
            "has_location": _snapshot_has_location(current),
        },
        "previous_snapshot": (
            {
                "observed_at": previous.observed_at.isoformat(),
                "odometer_km": previous.odometer_km,
                "speed_kph": previous.speed_kph,
                "has_location": _snapshot_has_location(previous),
            }
            if previous is not None
            else None
        ),
        "signals": {
            "moving": signals["moving"],
            "odometer_moving": signals["odometer_moving"],
            "speed_moving": signals["speed_moving"],
            "gps_moving": signals["gps_moving"],
            "odometer_delta_km": (
                round(float(signals["odometer_delta_km"]), 3)
                if signals["odometer_delta_km"] is not None
                else None
            ),
            "gps_distance_m": (
                round(float(signals["gps_distance_m"]), 1)
                if signals["gps_distance_m"] is not None
                else None
            ),
            "gps_threshold_m": round(float(signals["gps_threshold_m"]), 1),
            "speed_threshold_kph": round(float(signals["speed_threshold_kph"]), 1),
        },
        "open_trip_id": open_trip.id if open_trip is not None else None,
        "latest_trip": (
            {
                "id": latest_trip.id,
                "is_open": latest_trip.is_open,
                "distance_km": round(latest_trip.distance_km, 1),
                "started_at": latest_trip.started_at.isoformat(),
                "ended_at": latest_trip.ended_at.isoformat() if latest_trip.ended_at else None,
            }
            if latest_trip is not None
            else None
        ),
        "decision": decision,
    }


def save_snapshot(
    session: Session,
    reading: VehicleReading,
    provider_name: str,
    settings: Settings,
) -> tuple[Vehicle, Snapshot]:
    vehicle = session.scalar(
        select(Vehicle)
        .where(Vehicle.provider_vehicle_id == reading.provider_vehicle_id)
        .limit(1)
    )
    if vehicle is None:
        vehicle = Vehicle(
            provider=provider_name,
            provider_vehicle_id=reading.provider_vehicle_id,
            display_name=reading.display_name,
            make=reading.make,
            model=reading.model,
            year=reading.year,
        )
        session.add(vehicle)
        session.flush()
    else:
        vehicle.display_name = reading.display_name or vehicle.display_name
        vehicle.make = reading.make or vehicle.make
        vehicle.model = reading.model or vehicle.model
        vehicle.year = reading.year or vehicle.year

    previous = session.scalar(
        select(Snapshot)
        .where(Snapshot.vehicle_id == vehicle.id)
        .order_by(Snapshot.observed_at.desc())
        .limit(1)
    )
    raw_json = json.dumps(reading.raw, separators=(",", ":"), default=str) if reading.raw else None
    snapshot = Snapshot(
        vehicle_id=vehicle.id,
        observed_at=as_utc_naive(reading.observed_at) or utcnow(),
        source_updated_at=as_utc_naive(reading.source_updated_at),
        odometer_km=reading.odometer_km,
        fuel_percent=reading.fuel_percent,
        range_km=reading.range_km,
        speed_kph=reading.speed_kph,
        latitude=reading.latitude if settings.store_location else None,
        longitude=reading.longitude if settings.store_location else None,
        raw_json=raw_json,
    )
    session.add(snapshot)
    session.flush()
    _update_trip(session, previous, snapshot, settings)
    return vehicle, snapshot


def add_fuel_fill(
    session: Session,
    vehicle: Vehicle,
    liters: float,
    total_cost: float,
    odometer_km: float | None = None,
    station: str | None = None,
    notes: str | None = None,
    filled_at: datetime | None = None,
) -> FuelFill:
    if odometer_km is None:
        latest = session.scalar(
            select(Snapshot)
            .where(Snapshot.vehicle_id == vehicle.id)
            .order_by(Snapshot.observed_at.desc())
            .limit(1)
        )
        if latest is not None:
            odometer_km = latest.odometer_km
    fill = FuelFill(
        vehicle_id=vehicle.id,
        filled_at=as_utc_naive(filled_at) or utcnow(),
        liters=liters,
        total_cost=total_cost,
        odometer_km=odometer_km,
        station=station,
        notes=notes,
    )
    session.add(fill)
    session.flush()
    return fill
