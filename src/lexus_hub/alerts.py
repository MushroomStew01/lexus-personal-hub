from __future__ import annotations

"""Send optional alerts about the account owner's own vehicle to their configured Discord webhook."""

import logging
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import NotificationLog, Snapshot, Vehicle
from .timeutil import utcnow

_LOGGER = logging.getLogger(__name__)
_ALERT_COOLDOWN = timedelta(hours=12)
_SERVICE_WARNING_KM = 800


def _recently_sent(session: Session, key: str) -> bool:
    cutoff = utcnow() - _ALERT_COOLDOWN
    return (
        session.scalar(
            select(NotificationLog.id)
            .where(
                NotificationLog.event_key == key,
                NotificationLog.created_at >= cutoff,
            )
            .limit(1)
        )
        is not None
    )


def pending_alerts(
    session: Session,
    vehicle: Vehicle,
    snapshot: Snapshot,
    settings: Settings,
) -> list[tuple[str, str]]:
    alerts: list[tuple[str, str]] = []
    label = vehicle.display_name

    if (
        snapshot.fuel_percent is not None
        and snapshot.fuel_percent <= settings.low_fuel_percent
        and not _recently_sent(session, "low_fuel")
    ):
        alerts.append(("low_fuel", f"⛽ {label}: fuel is {snapshot.fuel_percent:.0f}%."))

    if (
        snapshot.range_km is not None
        and snapshot.range_km <= settings.low_range_km
        and not _recently_sent(session, "low_range")
    ):
        alerts.append(("low_range", f"🛣️ {label}: range is {snapshot.range_km:.0f} km."))

    if settings.last_service_odometer_km is not None and snapshot.odometer_km is not None:
        next_service = settings.last_service_odometer_km + settings.service_interval_km
        remaining = next_service - snapshot.odometer_km
        if remaining <= _SERVICE_WARNING_KM and not _recently_sent(session, "service_due"):
            if remaining <= 0:
                message = f"🔧 {label}: service is overdue by {abs(remaining):.0f} km."
            else:
                message = f"🔧 {label}: service is due in about {remaining:.0f} km."
            alerts.append(("service_due", message))

    return alerts


async def deliver_alerts(
    session: Session,
    vehicle: Vehicle,
    snapshot: Snapshot,
    settings: Settings,
) -> list[str]:
    if not settings.discord_webhook_url:
        return []

    delivered: list[str] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for key, message in pending_alerts(session, vehicle, snapshot, settings):
            try:
                response = await client.post(settings.discord_webhook_url, json={"content": message})
                response.raise_for_status()
            except httpx.HTTPError:
                _LOGGER.exception("Discord webhook delivery failed for %s", key)
                continue
            session.add(
                NotificationLog(
                    event_key=key,
                    created_at=utcnow(),
                    channel="discord",
                    message=message,
                )
            )
            delivered.append(message)
    return delivered
