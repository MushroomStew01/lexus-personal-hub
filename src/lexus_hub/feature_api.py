from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .config import get_settings
from .db import init_db, session_scope
from .insights import (
    add_maintenance_record,
    add_named_location_from_current,
    current_vehicle_location,
    fuel_analytics,
    maintenance_history,
    named_locations,
    trip_replay,
    vehicle_timeline,
    weekly_summary,
)

router = APIRouter(tags=["vehicle insights"])


class NamedLocationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    radius_m: float | None = Field(default=None, ge=25, le=5000)
    is_private: bool = False


class MaintenanceRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    odometer_km: float | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)
    next_due_km: float | None = Field(default=None, ge=0)


@router.get("/api/where")
def api_where() -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return current_vehicle_location(session, settings)


@router.get("/api/locations")
def api_locations() -> list[dict[str, object]]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return named_locations(session, settings)


@router.post("/api/locations/current", status_code=201)
def api_add_current_location(payload: NamedLocationRequest) -> dict[str, object]:
    settings = get_settings()
    if not settings.store_location:
        raise HTTPException(status_code=409, detail="Set STORE_LOCATION=true first.")
    init_db()
    try:
        with session_scope() as session:
            location = add_named_location_from_current(
                session,
                settings,
                name=payload.name,
                radius_m=payload.radius_m,
                is_private=payload.is_private,
            )
            return {
                "id": location.id,
                "name": location.name,
                "radius_m": location.radius_m,
                "is_private": location.is_private,
            }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/trips/{trip_id}/replay")
def api_trip_replay(trip_id: int) -> dict[str, object]:
    settings = get_settings()
    if not settings.store_location:
        raise HTTPException(status_code=409, detail="Set STORE_LOCATION=true first.")
    if not settings.show_exact_location:
        raise HTTPException(status_code=403, detail="Set SHOW_EXACT_LOCATION=true first.")
    init_db()
    with session_scope() as session:
        replay = trip_replay(session, settings, trip_id)
    if replay is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return replay


@router.get("/api/fuel/analytics")
def api_fuel_analytics() -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return fuel_analytics(session, settings)


@router.get("/api/timeline")
def api_timeline(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[dict[str, object]]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return vehicle_timeline(session, settings, limit=limit)


@router.get("/api/maintenance")
def api_maintenance(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[dict[str, object]]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return maintenance_history(session, settings, limit=limit)


@router.post("/api/maintenance", status_code=201)
def api_add_maintenance(payload: MaintenanceRequest) -> dict[str, object]:
    settings = get_settings()
    init_db()
    try:
        with session_scope() as session:
            record = add_maintenance_record(
                session,
                settings,
                kind=payload.kind,
                odometer_km=payload.odometer_km,
                cost=payload.cost,
                notes=payload.notes,
                next_due_km=payload.next_due_km,
            )
            return {
                "id": record.id,
                "kind": record.kind,
                "odometer_km": record.odometer_km,
                "cost": record.cost,
                "next_due_km": record.next_due_km,
            }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/weekly")
def api_weekly() -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return weekly_summary(session, settings)
