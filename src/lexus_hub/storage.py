from __future__ import annotations

"""Local persistence for the account owner's own vehicle telemetry.

This module does not collect location data and does not expose data to third parties.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import FuelFill, Snapshot, Vehicle
from .providers.base import VehicleReading
from .timeutil import as_utc_naive, utcnow


def primary_vehicle(session: Session, settings: Settings) -> Vehicle | None:
    provider_id = "ha:primary" if settings.provider == "home_assistant" else "mock:primary"
    return session.scalar(
        select(Vehicle).where(Vehicle.provider_vehicle_id == provider_id).limit(1)
    )


def save_snapshot(
    session: Session,
    reading: VehicleReading,
    provider_name: str,
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
