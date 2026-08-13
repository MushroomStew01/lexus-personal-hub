from __future__ import annotations

"""Periodically save telemetry from the account owner's configured vehicle provider."""

import asyncio
import logging
from typing import Any

from .alerts import deliver_alerts
from .config import Settings, get_settings
from .db import init_db, session_scope
from .providers import get_provider
from .storage import save_snapshot

_LOGGER = logging.getLogger(__name__)


async def poll_once(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = get_provider(settings)
    reading = await provider.fetch()
    init_db()
    with session_scope() as session:
        vehicle, snapshot = save_snapshot(session, reading, provider.name, settings)
        alerts = await deliver_alerts(session, vehicle, snapshot, settings)
        return {
            "provider": provider.name,
            "vehicle": vehicle.display_name,
            "observed_at": snapshot.observed_at.isoformat(),
            "odometer_km": snapshot.odometer_km,
            "fuel_percent": snapshot.fuel_percent,
            "range_km": snapshot.range_km,
            "speed_kph": snapshot.speed_kph,
            "alerts_delivered": alerts,
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
