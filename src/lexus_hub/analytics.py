from __future__ import annotations

"""Aggregate the account owner's locally stored vehicle history for the dashboard."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .models import FuelFill, Snapshot, Trip
from .storage import primary_vehicle
from .timeutil import utcnow


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.isoformat()


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
    fuel_spend_30d = session.scalar(
        select(func.coalesce(func.sum(FuelFill.total_cost), 0.0)).where(
            FuelFill.vehicle_id == vehicle.id,
            FuelFill.filled_at >= cutoff_30d,
        )
    )

    next_service = None
    service_remaining = None
    if settings.last_service_odometer_km is not None:
        next_service = settings.last_service_odometer_km + settings.service_interval_km
        if latest and latest.odometer_km is not None:
            service_remaining = next_service - latest.odometer_km

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
        "last_poll": _iso(latest.observed_at) if latest else None,
        "source_updated_at": _iso(latest.source_updated_at) if latest else None,
        "distance_7d_km": round(float(distance_7d or 0.0), 1),
        "distance_30d_km": round(float(distance_30d or 0.0), 1),
        "fuel_spend_30d": round(float(fuel_spend_30d or 0.0), 2),
        "next_service_odometer_km": next_service,
        "service_remaining_km": service_remaining,
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
            "started_at": _iso(trip.started_at),
            "ended_at": _iso(trip.ended_at),
            "distance_km": round(trip.distance_km, 1),
            "is_open": trip.is_open,
        }
        for trip in trips
    ]


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
            "filled_at": _iso(fill.filled_at),
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
