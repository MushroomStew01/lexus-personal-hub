from __future__ import annotations

"""Periodically save telemetry from the account owner's configured vehicle provider."""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from .alerts import deliver_alerts, deliver_trip_summary, deliver_weekly_report
from .config import Settings, get_settings
from .db import init_db, session_scope
from .ha_refresh import request_vehicle_refresh
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

        stop_detected = False
        if open_trip_id is not None:
            active_trip = session.get(Trip, open_trip_id)
            if active_trip is not None and active_trip.is_open:
                idle = snapshot.observed_at - active_trip.last_movement_at
                first_idle_window = timedelta(
                    minutes=max(5.0, settings.poll_interval_minutes * 1.5)
                )
                stop_detected = timedelta(0) < idle <= first_idle_window

        alerts = await deliver_alerts(session, vehicle, snapshot, settings)

        trip_summary = None
        completed_trip_id = None
        if open_trip_id is not None:
            completed_trip = session.get(Trip, open_trip_id)
            if completed_trip is not None and not completed_trip.is_open:
                completed_trip_id = completed_trip.id
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
            "stop_detected": stop_detected,
            "completed_trip_id": completed_trip_id,
            "alerts_delivered": alerts,
            "trip_summary_delivered": trip_summary,
            "weekly_report_delivered": weekly_report,
        }


async def _confirm_post_stop_status(settings: Settings) -> None:
    if settings.post_stop_refresh_delay_seconds:
        await asyncio.sleep(settings.post_stop_refresh_delay_seconds)

    refresh_result: dict[str, object]
    try:
        refresh_result = await request_vehicle_refresh(settings)
    except Exception:
        _LOGGER.exception("Home Assistant vehicle-status refresh request failed")
        refresh_result = {"requested": False, "reason": "Refresh request failed."}

    if refresh_result.get("requested") and settings.ha_refresh_settle_seconds:
        await asyncio.sleep(settings.ha_refresh_settle_seconds)

    try:
        result = await poll_once(settings)
    except Exception:
        _LOGGER.exception("Post-stop confirmation poll failed")
        return

    _LOGGER.info(
        "Post-stop status confirmation saved: refresh=%s snapshot=%s",
        refresh_result.get("requested"),
        result.get("observed_at"),
    )


async def poll_forever(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    while True:
        try:
            result = await poll_once(settings)
            if result.get("stop_detected") and settings.post_stop_refresh_enabled:
                await _confirm_post_stop_status(settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Vehicle polling failed")
        await asyncio.sleep(settings.poll_interval_minutes * 60)
