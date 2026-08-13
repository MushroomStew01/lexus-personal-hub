from __future__ import annotations

"""Local persistence for the account owner's own vehicle telemetry.

This module stores odometer/fuel/range/speed locally and derives trip distance from the owner's
odometer history. It does not collect location data or expose data to third parties.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import FuelFill, Snapshot, Trip, Vehicle
from .providers.base import VehicleReading
from .timeutil import as_utc_naive, utcnow


def primary_vehicle(session: Session, settings: Settings) -> Vehicle | None:
    provider_id = "ha:primary" if settings.provider == "home_assistant" else "mock:primary"
    return session.scalar(
        select(Vehicle).where(Vehicle.provider_vehicle_id == provider_id).limit(1)
    )


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
    if previous is None or previous.odometer_km is None or current.odometer_km is None:
        return

    gap = current.observed_at - previous.observed_at
    if gap < timedelta(0) or gap > timedelta(hours=settings.max_snapshot_gap_hours):
        if open_trip is not None:
            open_trip.ended_at = open_trip.last_movement_at
            open_trip.is_open = False
        return

    delta = current.odometer_km - previous.odometer_km
    if delta < -0.01:
        return

    if open_trip is None:
        if delta < settings.min_trip_delta_km:
            return
        session.add(
            Trip(
                vehicle_id=current.vehicle_id,
                started_at=previous.observed_at,
                ended_at=None,
                last_movement_at=current.observed_at,
                start_odometer_km=previous.odometer_km,
                end_odometer_km=current.odometer_km,
                distance_km=max(0.0, delta),
                is_open=True,
            )
        )
        return

    if current.odometer_km > open_trip.end_odometer_km + 0.01:
        open_trip.end_odometer_km = current.odometer_km
        open_trip.distance_km = max(
            0.0,
            current.odometer_km - open_trip.start_odometer_km,
        )
        open_trip.last_movement_at = current.observed_at
        return

    idle = current.observed_at - open_trip.last_movement_at
    if idle >= timedelta(minutes=settings.trip_idle_close_minutes):
        open_trip.ended_at = open_trip.last_movement_at
        open_trip.is_open = False


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
    snapshot = Snapshot(
        vehicle_id=vehicle.id,
        observed_at=as_utc_naive(reading.observed_at) or utcnow(),
        source_updated_at=as_utc_naive(reading.source_updated_at),
        odometer_km=reading.odometer_km,
        fuel_percent=reading.fuel_percent,
        range_km=reading.range_km,
        speed_kph=reading.speed_kph,
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
