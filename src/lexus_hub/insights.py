from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .models import FuelFill, MaintenanceRecord, NamedLocation, Snapshot, Trip, Vehicle
from .storage import primary_vehicle
from .timeutil import as_utc_naive, utcnow

_STATUS_LABELS = {
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
    "front_driver_door_lock": "Front driver lock",
    "front_passenger_door_lock": "Front passenger lock",
    "rear_driver_door_lock": "Rear driver lock",
    "rear_passenger_door_lock": "Rear passenger lock",
    "trunk_door_lock": "Trunk lock",
}


def _local_iso(value: datetime | None, settings: Settings) -> str | None:
    if value is None:
        return None
    source = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return source.astimezone(ZoneInfo(settings.timezone)).isoformat()


def _snapshot_status(snapshot: Snapshot | None) -> dict[str, object]:
    if snapshot is None or not snapshot.raw_json:
        return {}
    try:
        payload = json.loads(snapshot.raw_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    status = payload.get("status") if isinstance(payload, dict) else None
    return status if isinstance(status, dict) else {}


def _record_display(status: dict[str, object], key: str) -> str | None:
    record = status.get(key)
    if not isinstance(record, dict):
        return None
    value = record.get("display") or record.get("value")
    return str(value) if value is not None else None


def haversine_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius_m = 6_371_008.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def match_named_location(
    session: Session,
    vehicle_id: int,
    latitude: float | None,
    longitude: float | None,
) -> tuple[NamedLocation, float] | None:
    if latitude is None or longitude is None:
        return None
    locations = session.scalars(
        select(NamedLocation).where(NamedLocation.vehicle_id == vehicle_id)
    ).all()
    matches: list[tuple[NamedLocation, float]] = []
    for location in locations:
        distance = haversine_m(latitude, longitude, location.latitude, location.longitude)
        if distance <= location.radius_m:
            matches.append((location, distance))
    if not matches:
        return None
    return min(matches, key=lambda item: item[1])


def location_label(
    session: Session,
    vehicle_id: int,
    latitude: float | None,
    longitude: float | None,
    *,
    reveal_private_name: bool = False,
    reveal_coordinates: bool = False,
) -> str:
    if latitude is None or longitude is None:
        return "Unknown location"
    match = match_named_location(session, vehicle_id, latitude, longitude)
    if match is not None:
        location, _distance = match
        if location.is_private and not reveal_private_name:
            return "Private location"
        return location.name
    if reveal_coordinates:
        return f"{latitude:.5f}, {longitude:.5f}"
    return "Unnamed location"


def add_named_location_from_current(
    session: Session,
    settings: Settings,
    name: str,
    radius_m: float | None = None,
    is_private: bool = False,
) -> NamedLocation:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        raise ValueError("No vehicle data is available yet.")
    latest = session.scalar(
        select(Snapshot)
        .where(
            Snapshot.vehicle_id == vehicle.id,
            Snapshot.latitude.is_not(None),
            Snapshot.longitude.is_not(None),
        )
        .order_by(Snapshot.observed_at.desc())
        .limit(1)
    )
    if latest is None or latest.latitude is None or latest.longitude is None:
        raise ValueError("No stored Lexus location is available yet.")

    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Location name cannot be blank.")
    existing = session.scalar(
        select(NamedLocation)
        .where(
            NamedLocation.vehicle_id == vehicle.id,
            func.lower(NamedLocation.name) == normalized_name.lower(),
        )
        .limit(1)
    )
    if existing is None:
        existing = NamedLocation(
            vehicle_id=vehicle.id,
            name=normalized_name,
            latitude=float(latest.latitude),
            longitude=float(latest.longitude),
            radius_m=radius_m or settings.named_location_default_radius_m,
            is_private=is_private,
        )
        session.add(existing)
    else:
        existing.latitude = float(latest.latitude)
        existing.longitude = float(latest.longitude)
        existing.radius_m = radius_m or settings.named_location_default_radius_m
        existing.is_private = is_private
    session.flush()
    return existing


def named_locations(session: Session, settings: Settings) -> list[dict[str, object]]:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return []
    rows = session.scalars(
        select(NamedLocation)
        .where(NamedLocation.vehicle_id == vehicle.id)
        .order_by(NamedLocation.name.asc())
    ).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "radius_m": round(row.radius_m),
            "is_private": row.is_private,
        }
        for row in rows
    ]


def current_vehicle_location(session: Session, settings: Settings) -> dict[str, object]:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return {"ready": False}
    latest = session.scalar(
        select(Snapshot)
        .where(Snapshot.vehicle_id == vehicle.id)
        .order_by(Snapshot.observed_at.desc())
        .limit(1)
    )
    if latest is None:
        return {"ready": False}

    label = location_label(
        session,
        vehicle.id,
        latest.latitude,
        latest.longitude,
        reveal_private_name=False,
        reveal_coordinates=False,
    )
    latest_trip = session.scalar(
        select(Trip)
        .where(Trip.vehicle_id == vehicle.id)
        .order_by(Trip.started_at.desc())
        .limit(1)
    )
    parked_since = None
    if (
        latest_trip is not None
        and not latest_trip.is_open
        and latest_trip.ended_at is not None
        and (latest.speed_kph is None or latest.speed_kph <= settings.parking_speed_threshold_kph)
    ):
        parked_since = latest_trip.ended_at

    result: dict[str, object] = {
        "ready": True,
        "label": label,
        "observed_at": _local_iso(latest.observed_at, settings),
        "parked_since": _local_iso(parked_since, settings),
        "fuel_percent": latest.fuel_percent,
        "range_km": latest.range_km,
        "odometer_km": latest.odometer_km,
        "speed_kph": latest.speed_kph,
    }
    if settings.show_exact_location and latest.latitude is not None and latest.longitude is not None:
        result["latitude"] = latest.latitude
        result["longitude"] = latest.longitude
    return result


def trip_labels(session: Session, trip: Trip) -> tuple[str, str]:
    return (
        location_label(
            session,
            trip.vehicle_id,
            trip.start_latitude,
            trip.start_longitude,
        ),
        location_label(
            session,
            trip.vehicle_id,
            trip.end_latitude,
            trip.end_longitude,
        ),
    )


def trip_replay(
    session: Session,
    settings: Settings,
    trip_id: int,
) -> dict[str, object] | None:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return None
    trip = session.scalar(
        select(Trip).where(Trip.id == trip_id, Trip.vehicle_id == vehicle.id).limit(1)
    )
    if trip is None:
        return None
    replay_end = trip.ended_at or trip.last_movement_at
    snapshots = session.scalars(
        select(Snapshot)
        .where(
            Snapshot.vehicle_id == vehicle.id,
            Snapshot.observed_at >= trip.started_at,
            Snapshot.observed_at <= replay_end,
        )
        .order_by(Snapshot.observed_at.asc())
    ).all()
    points = []
    for snapshot in snapshots:
        if snapshot.latitude is None or snapshot.longitude is None:
            continue
        points.append(
            {
                "observed_at": _local_iso(snapshot.observed_at, settings),
                "latitude": snapshot.latitude,
                "longitude": snapshot.longitude,
                "odometer_km": snapshot.odometer_km,
                "fuel_percent": snapshot.fuel_percent,
                "speed_kph": snapshot.speed_kph,
            }
        )
    start_label, end_label = trip_labels(session, trip)
    return {
        "id": trip.id,
        "started_at": _local_iso(trip.started_at, settings),
        "ended_at": _local_iso(trip.ended_at, settings),
        "distance_km": round(trip.distance_km, 1),
        "start_label": start_label,
        "end_label": end_label,
        "points": points,
    }


def fuel_analytics(session: Session, settings: Settings) -> dict[str, object]:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return {"ready": False}
    fills = session.scalars(
        select(FuelFill)
        .where(FuelFill.vehicle_id == vehicle.id)
        .order_by(FuelFill.filled_at.asc())
    ).all()
    cutoff = utcnow() - timedelta(days=30)
    recent = [fill for fill in fills if fill.filled_at >= cutoff]
    intervals: list[dict[str, object]] = []
    total_distance = 0.0
    total_liters = 0.0
    total_cost = 0.0
    for previous, current in zip(fills, fills[1:], strict=False):
        if previous.odometer_km is None or current.odometer_km is None:
            continue
        distance = current.odometer_km - previous.odometer_km
        if distance <= 0:
            continue
        economy = current.liters / distance * 100
        cost_per_km = current.total_cost / distance
        total_distance += distance
        total_liters += current.liters
        total_cost += current.total_cost
        intervals.append(
            {
                "filled_at": _local_iso(current.filled_at, settings),
                "distance_km": round(distance, 1),
                "liters_per_100km": round(economy, 2),
                "cost_per_km": round(cost_per_km, 3),
            }
        )
    return {
        "ready": True,
        "fill_count": len(fills),
        "fill_count_30d": len(recent),
        "spend_30d": round(sum(fill.total_cost for fill in recent), 2),
        "liters_30d": round(sum(fill.liters for fill in recent), 1),
        "average_l_per_100km": (
            round(total_liters / total_distance * 100, 2) if total_distance > 0 else None
        ),
        "average_cost_per_km": (
            round(total_cost / total_distance, 3) if total_distance > 0 else None
        ),
        "latest_interval": intervals[-1] if intervals else None,
        "intervals": list(reversed(intervals[-10:])),
    }


def add_maintenance_record(
    session: Session,
    settings: Settings,
    kind: str,
    odometer_km: float | None = None,
    cost: float | None = None,
    notes: str | None = None,
    next_due_km: float | None = None,
    next_due_at: datetime | None = None,
    performed_at: datetime | None = None,
) -> MaintenanceRecord:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        raise ValueError("No vehicle data is available yet.")
    if odometer_km is None:
        latest = session.scalar(
            select(Snapshot)
            .where(Snapshot.vehicle_id == vehicle.id)
            .order_by(Snapshot.observed_at.desc())
            .limit(1)
        )
        odometer_km = latest.odometer_km if latest is not None else None
    record = MaintenanceRecord(
        vehicle_id=vehicle.id,
        performed_at=as_utc_naive(performed_at) or utcnow(),
        kind=kind.strip() or "Maintenance",
        odometer_km=odometer_km,
        cost=cost,
        notes=notes,
        next_due_km=next_due_km,
        next_due_at=as_utc_naive(next_due_at),
    )
    session.add(record)
    session.flush()
    return record


def maintenance_history(
    session: Session,
    settings: Settings,
    limit: int = 20,
) -> list[dict[str, object]]:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return []
    records = session.scalars(
        select(MaintenanceRecord)
        .where(MaintenanceRecord.vehicle_id == vehicle.id)
        .order_by(MaintenanceRecord.performed_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": record.id,
            "performed_at": _local_iso(record.performed_at, settings),
            "kind": record.kind,
            "odometer_km": record.odometer_km,
            "cost": record.cost,
            "notes": record.notes,
            "next_due_km": record.next_due_km,
            "next_due_at": _local_iso(record.next_due_at, settings),
        }
        for record in records
    ]


def vehicle_timeline(
    session: Session,
    settings: Settings,
    limit: int = 20,
) -> list[dict[str, object]]:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return []
    events: list[tuple[datetime, str, str]] = []

    trips = session.scalars(
        select(Trip)
        .where(Trip.vehicle_id == vehicle.id)
        .order_by(Trip.started_at.desc())
        .limit(12)
    ).all()
    for trip in trips:
        start_label, end_label = trip_labels(session, trip)
        events.append(
            (trip.started_at, "trip_start", f"Trip started from {start_label}")
        )
        if trip.ended_at is not None:
            events.append(
                (
                    trip.ended_at,
                    "trip_end",
                    f"Trip completed at {end_label} · {trip.distance_km:.1f} km",
                )
            )

    fills = session.scalars(
        select(FuelFill)
        .where(FuelFill.vehicle_id == vehicle.id)
        .order_by(FuelFill.filled_at.desc())
        .limit(8)
    ).all()
    for fill in fills:
        events.append(
            (
                fill.filled_at,
                "fuel",
                f"Fuel fill · {fill.liters:.1f} L · ${fill.total_cost:.2f}",
            )
        )

    maintenance = session.scalars(
        select(MaintenanceRecord)
        .where(MaintenanceRecord.vehicle_id == vehicle.id)
        .order_by(MaintenanceRecord.performed_at.desc())
        .limit(8)
    ).all()
    for record in maintenance:
        events.append((record.performed_at, "maintenance", record.kind))

    snapshots = list(
        reversed(
            session.scalars(
                select(Snapshot)
                .where(Snapshot.vehicle_id == vehicle.id)
                .order_by(Snapshot.observed_at.desc())
                .limit(40)
            ).all()
        )
    )
    previous_status: dict[str, object] | None = None
    for snapshot in snapshots:
        status = _snapshot_status(snapshot)
        if previous_status is not None:
            for key, label in _STATUS_LABELS.items():
                before = _record_display(previous_status, key)
                after = _record_display(status, key)
                if before is not None and after is not None and before != after:
                    events.append((snapshot.observed_at, "status", f"{label}: {after}"))
        previous_status = status

    events.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "at": _local_iso(at, settings),
            "type": event_type,
            "text": text,
        }
        for at, event_type, text in events[:limit]
    ]


def weekly_summary(session: Session, settings: Settings) -> dict[str, object]:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return {"ready": False}
    cutoff = utcnow() - timedelta(days=7)
    trips = session.scalars(
        select(Trip).where(Trip.vehicle_id == vehicle.id, Trip.started_at >= cutoff)
    ).all()
    fills = session.scalars(
        select(FuelFill).where(FuelFill.vehicle_id == vehicle.id, FuelFill.filled_at >= cutoff)
    ).all()
    latest = session.scalar(
        select(Snapshot)
        .where(Snapshot.vehicle_id == vehicle.id)
        .order_by(Snapshot.observed_at.desc())
        .limit(1)
    )
    status = _snapshot_status(latest)
    tires = {
        key: _record_display(status, key)
        for key in (
            "front_driver_tire",
            "front_passenger_tire",
            "rear_driver_tire",
            "rear_passenger_tire",
        )
    }
    return {
        "ready": True,
        "distance_km": round(sum(trip.distance_km for trip in trips), 1),
        "trip_count": len(trips),
        "average_trip_km": (
            round(sum(trip.distance_km for trip in trips) / len(trips), 1) if trips else 0.0
        ),
        "longest_trip_km": round(max((trip.distance_km for trip in trips), default=0.0), 1),
        "fuel_spend": round(sum(fill.total_cost for fill in fills), 2),
        "fuel_liters": round(sum(fill.liters for fill in fills), 1),
        "odometer_km": latest.odometer_km if latest is not None else None,
        "fuel_percent": latest.fuel_percent if latest is not None else None,
        "range_km": latest.range_km if latest is not None else None,
        "tires": tires,
    }
