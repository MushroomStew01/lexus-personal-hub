from __future__ import annotations

"""Periodically save telemetry from the account owner's configured vehicle provider."""

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from .alerts import deliver_alerts, deliver_trip_summary, deliver_weekly_report
from .config import Settings, get_settings
from .db import init_db, session_scope
from .models import Trip
from .providers import get_provider
from .storage import primary_vehicle, save_snapshot

_LOGGER = logging.getLogger(__name__)


async def poll_once(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = get_provider(settings)
    reading = await provider.fetch()
    init_db()
    with session_scope() as session:
        before_vehicle = primary_vehicle(session, settings)
        open_trip_id = None
        if before_vehicle is not None:
            open_trip_id = session.scalar(
                select(Trip.id)
                .where(Trip.vehicle_id == before_vehicle.id, Trip.is_open.is_(True))
                .order_by(Trip.started_at.desc())
                .limit(1)
            )

        vehicle, snapshot = save_snapshot(session, reading, provider.name, settings)
        alerts = await deliver_alerts(session, vehicle, snapshot, settings)

        trip_summary = None
        if open_trip_id is not None:
            completed_trip = session.get(Trip, open_trip_id)
            if completed_trip is not None and not completed_trip.is_open:
                trip_summary = await deliver_trip_summary(session, completed_trip, settings)

        weekly_report = await deliver_weekly_report(session, settings)
        return {
            "provider": provider.name,
            "vehicle": vehicle.display_name,
            "observed_at": snapshot.observed_at.isoformat(),
            "odometer_km": snapshot.odometer_km,
            "fuel_percent": snapshot.fuel_percent,
            "range_km": snapshot.range_km,
            "speed_kph": snapshot.speed_kph,
            "alerts_delivered": alerts,
            "trip_summary_delivered": trip_summary,
            "weekly_report_delivered": weekly_report,
        }


async def poll_forever(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    while True:
        try:
            await poll_once(settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Vehicle polling failed")
        await asyncio.sleep(settings.poll_interval_minutes * 60)
