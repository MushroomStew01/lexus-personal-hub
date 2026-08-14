from __future__ import annotations

"""Aggregate the account owner's locally stored vehicle history for the dashboard."""

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .models import FuelFill, Snapshot, Trip, TripPoint
from .storage import primary_vehicle
from .timeutil import utcnow


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


def status_summary(session: Session, settings: Settings) -> dict[str, object]:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return {"ready": False, "provider": settings.provider, "message": "No saved data yet."}

    latest = session.scalar(
        select(Snapshot)
        .where(Snapshot.vehicle_id == vehicle.id)
        .order_by(Snapshot.observed_at.desc())
        .limit(1)
    )
    cutoff_7d = utcnow() - timedelta(days=7)
    cutoff_30d = utcnow() - timedelta(days=30)
    distance_7d = session.scalar(
        select(func.coalesce(func.sum(Trip.distance_km), 0.0)).where(
            Trip.vehicle_id == vehicle.id,
            Trip.started_at >= cutoff_7d,
        )
    )
    distance_30d = session.scalar(
        select(func.coalesce(func.sum(Trip.distance_km), 0.0)).where(
            Trip.vehicle_id == vehicle.id,
            Trip.started_at >= cutoff_30d,
        )
    )
    trip_count_30d = session.scalar(
        select(func.count(Trip.id)).where(
            Trip.vehicle_id == vehicle.id,
            Trip.started_at >= cutoff_30d,
        )
    )
    fuel_spend_30d = session.scalar(
        select(func.coalesce(func.sum(FuelFill.total_cost), 0.0)).where(
            FuelFill.vehicle_id == vehicle.id,
            FuelFill.filled_at >= cutoff_30d,
        )
    )
    fuel_fill_count_30d = session.scalar(
        select(func.count(FuelFill.id)).where(
            FuelFill.vehicle_id == vehicle.id,
            FuelFill.filled_at >= cutoff_30d,
        )
    )
    latest_trip = session.scalar(
        select(Trip)
        .where(Trip.vehicle_id == vehicle.id)
        .order_by(Trip.started_at.desc())
        .limit(1)
    )

    next_service = None
    service_remaining = None
    if settings.last_service_odometer_km is not None:
        next_service = settings.last_service_odometer_km + settings.service_interval_km
        if latest and latest.odometer_km is not None:
            service_remaining = next_service - latest.odometer_km

    count = int(trip_count_30d or 0)
    distance_30 = float(distance_30d or 0.0)
    return {
        "ready": latest is not None,
        "provider": vehicle.provider,
        "vehicle": {
            "display_name": vehicle.display_name,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
        },
        "odometer_km": latest.odometer_km if latest else None,
        "fuel_percent": latest.fuel_percent if latest else None,
        "range_km": latest.range_km if latest else None,
        "speed_kph": latest.speed_kph if latest else None,
        "last_poll": _local_iso(latest.observed_at, settings) if latest else None,
        "source_updated_at": _local_iso(latest.source_updated_at, settings) if latest else None,
        "distance_7d_km": round(float(distance_7d or 0.0), 1),
        "distance_30d_km": round(distance_30, 1),
        "trip_count_30d": count,
        "average_trip_30d_km": round(distance_30 / count, 1) if count else 0.0,
        "fuel_spend_30d": round(float(fuel_spend_30d or 0.0), 2),
        "fuel_fill_count_30d": int(fuel_fill_count_30d or 0),
        "next_service_odometer_km": next_service,
        "service_remaining_km": service_remaining,
        "vehicle_status": _snapshot_status(latest),
        "location_storage_enabled": settings.store_location,
        "trip_maps_enabled": settings.store_location and settings.show_exact_location,
        "last_trip": (
            {
                "started_at": _local_iso(latest_trip.started_at, settings),
                "ended_at": _local_iso(latest_trip.ended_at, settings),
                "distance_km": round(latest_trip.distance_km, 1),
                "is_open": latest_trip.is_open,
            }
            if latest_trip
            else None
        ),
    }


def recent_trips(
    session: Session,
    settings: Settings,
    limit: int = 20,
) -> list[dict[str, object]]:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return []
    trips = session.scalars(
        select(Trip)
        .where(Trip.vehicle_id == vehicle.id)
        .order_by(Trip.started_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": trip.id,
            "started_at": _local_iso(trip.started_at, settings),
            "ended_at": _local_iso(trip.ended_at, settings),
            "distance_km": round(trip.distance_km, 1),
            "is_open": trip.is_open,
            "has_route": bool(
                len(trip.points) >= 2
                or (
                    trip.start_latitude is not None
                    and trip.start_longitude is not None
                    and trip.end_latitude is not None
                    and trip.end_longitude is not None
                )
            ),
        }
        for trip in trips
    ]


def trip_route(
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

    points = session.scalars(
        select(TripPoint)
        .where(TripPoint.trip_id == trip.id)
        .order_by(TripPoint.observed_at.asc())
    ).all()
    coordinates = [
        {
            "latitude": point.latitude,
            "longitude": point.longitude,
            "observed_at": _local_iso(point.observed_at, settings),
        }
        for point in points
    ]

    if len(coordinates) < 2:
        coordinates = []
        if trip.start_latitude is not None and trip.start_longitude is not None:
            coordinates.append(
                {
                    "latitude": trip.start_latitude,
                    "longitude": trip.start_longitude,
                    "observed_at": _local_iso(trip.started_at, settings),
                }
            )
        if trip.end_latitude is not None and trip.end_longitude is not None:
            end_point = {
                "latitude": trip.end_latitude,
                "longitude": trip.end_longitude,
                "observed_at": _local_iso(trip.ended_at or trip.last_movement_at, settings),
            }
            if not coordinates or (
                coordinates[-1]["latitude"] != end_point["latitude"]
                or coordinates[-1]["longitude"] != end_point["longitude"]
            ):
                coordinates.append(end_point)

    return {
        "id": trip.id,
        "started_at": _local_iso(trip.started_at, settings),
        "ended_at": _local_iso(trip.ended_at, settings),
        "distance_km": round(trip.distance_km, 1),
        "is_open": trip.is_open,
        "point_count": len(coordinates),
        "points": coordinates,
    }


def recent_fuel_fills(
    session: Session,
    settings: Settings,
    limit: int = 20,
) -> list[dict[str, object]]:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return []
    fills = session.scalars(
        select(FuelFill)
        .where(FuelFill.vehicle_id == vehicle.id)
        .order_by(FuelFill.filled_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": fill.id,
            "filled_at": _local_iso(fill.filled_at, settings),
            "liters": fill.liters,
            "total_cost": fill.total_cost,
            "odometer_km": fill.odometer_km,
            "station": fill.station,
            "notes": fill.notes,
        }
        for fill in fills
    ]


def daily_distance(
    session: Session,
    settings: Settings,
    days: int = 30,
) -> list[dict[str, object]]:
    vehicle = primary_vehicle(session, settings)
    if vehicle is None:
        return []
    cutoff = utcnow() - timedelta(days=days)
    trips = session.scalars(
        select(Trip).where(Trip.vehicle_id == vehicle.id, Trip.started_at >= cutoff)
    ).all()
    timezone = ZoneInfo(settings.timezone)
    totals: dict[str, float] = defaultdict(float)
    for trip in trips:
        local = trip.started_at.replace(tzinfo=UTC).astimezone(timezone)
        totals[local.date().isoformat()] += trip.distance_km

    today = datetime.now(timezone).date()
    return [
        {
            "date": (today - timedelta(days=offset)).isoformat(),
            "distance_km": round(
                totals.get((today - timedelta(days=offset)).isoformat(), 0.0),
                1,
            ),
        }
        for offset in range(days - 1, -1, -1)
    ]
