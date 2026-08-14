from __future__ import annotations

"""Send optional alerts about the account owner's own vehicle to Discord."""

import json
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .insights import trip_labels, weekly_summary
from .models import NotificationLog, Snapshot, Trip, Vehicle
from .timeutil import utcnow

_LOGGER = logging.getLogger(__name__)
_ALERT_COOLDOWN = timedelta(hours=12)
_SERVICE_WARNING_KM = 800
_TIRE_KEYS = {
    "front_driver_tire": "front driver",
    "front_passenger_tire": "front passenger",
    "rear_driver_tire": "rear driver",
    "rear_passenger_tire": "rear passenger",
}
_OPENING_KEYS = {
    "front_driver_door": "front driver door",
    "front_passenger_door": "front passenger door",
    "rear_driver_door": "rear driver door",
    "rear_passenger_door": "rear passenger door",
    "front_driver_window": "front driver window",
    "front_passenger_window": "front passenger window",
    "rear_driver_window": "rear driver window",
    "rear_passenger_window": "rear passenger window",
    "moonroof": "moonroof",
    "hood": "hood",
    "trunk": "trunk",
}
_LOCK_KEYS = {
    "front_driver_door_lock": "front driver door",
    "front_passenger_door_lock": "front passenger door",
    "rear_driver_door_lock": "rear driver door",
    "rear_passenger_door_lock": "rear passenger door",
    "trunk_door_lock": "trunk",
}


def _recently_sent(
    session: Session,
    key: str,
    cooldown: timedelta = _ALERT_COOLDOWN,
) -> bool:
    cutoff = utcnow() - cooldown
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


def _ever_sent(session: Session, key: str) -> bool:
    return (
        session.scalar(
            select(NotificationLog.id)
            .where(NotificationLog.event_key == key)
            .limit(1)
        )
        is not None
    )


def _snapshot_status(snapshot: Snapshot) -> dict[str, object]:
    if not snapshot.raw_json:
        return {}
    try:
        payload = json.loads(snapshot.raw_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    status = payload.get("status") if isinstance(payload, dict) else None
    return status if isinstance(status, dict) else {}


def _record_value(status: dict[str, object], key: str) -> object:
    record = status.get(key)
    if not isinstance(record, dict):
        return None
    return record.get("value")


def _record_text(status: dict[str, object], key: str) -> str:
    value = _record_value(status, key)
    return str(value or "").strip().lower()


def _record_number(status: dict[str, object], key: str) -> float | None:
    value = _record_value(status, key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _vehicle_is_parked(
    session: Session,
    vehicle: Vehicle,
    snapshot: Snapshot,
    settings: Settings,
) -> bool:
    if snapshot.speed_kph is not None and snapshot.speed_kph > settings.parking_speed_threshold_kph:
        return False
    open_trip = session.scalar(
        select(Trip.id)
        .where(Trip.vehicle_id == vehicle.id, Trip.is_open.is_(True))
        .limit(1)
    )
    return open_trip is None


def pending_alerts(
    session: Session,
    vehicle: Vehicle,
    snapshot: Snapshot,
    settings: Settings,
) -> list[tuple[str, str]]:
    alerts: list[tuple[str, str]] = []
    label = vehicle.display_name
    status = _snapshot_status(snapshot)

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

    for key, tire_label in _TIRE_KEYS.items():
        pressure = _record_number(status, key)
        event_key = f"low_tire:{key}"
        if (
            pressure is not None
            and pressure < settings.low_tire_psi
            and not _recently_sent(session, event_key)
        ):
            alerts.append(
                (
                    event_key,
                    f"🛞 {label}: {tire_label} tire is {pressure:.0f} psi.",
                )
            )

    parked = _vehicle_is_parked(session, vehicle, snapshot, settings)
    if parked and settings.alert_openings:
        open_items = [
            item_label
            for key, item_label in _OPENING_KEYS.items()
            if _record_text(status, key) == "open"
        ]
        if open_items and not _recently_sent(session, "parked_opening", timedelta(hours=2)):
            alerts.append(
                (
                    "parked_opening",
                    f"⚠️ {label} is parked with open: {', '.join(open_items)}.",
                )
            )

    if parked and settings.alert_unlocked:
        unlocked = [
            item_label
            for key, item_label in _LOCK_KEYS.items()
            if _record_text(status, key) == "unlocked"
        ]
        if unlocked and not _recently_sent(session, "parked_unlocked", timedelta(hours=2)):
            alerts.append(
                (
                    "parked_unlocked",
                    f"🔓 {label} is parked but unlocked: {', '.join(unlocked)}.",
                )
            )

    if snapshot.source_updated_at is not None:
        age = utcnow() - snapshot.source_updated_at
        stale_after = timedelta(minutes=settings.stale_telemetry_minutes)
        if age >= stale_after and not _recently_sent(session, "stale_telemetry", stale_after):
            alerts.append(
                (
                    "stale_telemetry",
                    f"📡 {label}: Lexus telemetry has not updated for about "
                    f"{age.total_seconds() / 3600:.1f} hours.",
                )
            )

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


async def _post_webhook(settings: Settings, message: str) -> bool:
    if not settings.discord_webhook_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(settings.discord_webhook_url, json={"content": message})
            response.raise_for_status()
    except httpx.HTTPError:
        _LOGGER.exception("Discord webhook delivery failed")
        return False
    return True


def _log_notification(session: Session, key: str, message: str) -> None:
    session.add(
        NotificationLog(
            event_key=key,
            created_at=utcnow(),
            channel="discord",
            message=message,
        )
    )


async def deliver_alerts(
    session: Session,
    vehicle: Vehicle,
    snapshot: Snapshot,
    settings: Settings,
) -> list[str]:
    if not settings.discord_webhook_url:
        return []

    delivered: list[str] = []
    for key, message in pending_alerts(session, vehicle, snapshot, settings):
        if await _post_webhook(settings, message):
            _log_notification(session, key, message)
            delivered.append(message)
    return delivered


async def deliver_trip_summary(
    session: Session,
    trip: Trip,
    settings: Settings,
) -> str | None:
    if not settings.trip_summary_enabled or not settings.discord_webhook_url:
        return None
    event_key = f"trip_complete:{trip.id}"
    if _ever_sent(session, event_key):
        return None
    start_label, end_label = trip_labels(session, trip)
    duration = None
    if trip.ended_at is not None:
        duration = max(0, round((trip.ended_at - trip.started_at).total_seconds() / 60))
    duration_text = f" · {duration} min" if duration is not None else ""
    message = (
        f"🚗 **Trip completed**\n"
        f"{start_label} → {end_label}\n"
        f"{trip.distance_km:.1f} km{duration_text}"
    )
    if settings.dashboard_url:
        message += f"\n{settings.dashboard_url}"
    if not await _post_webhook(settings, message):
        return None
    _log_notification(session, event_key, message)
    return message


async def deliver_weekly_report(session: Session, settings: Settings) -> str | None:
    if not settings.weekly_report_enabled or not settings.discord_webhook_url:
        return None
    now_local = datetime.now(ZoneInfo(settings.timezone))
    if now_local.weekday() != settings.weekly_report_weekday or now_local.hour < settings.weekly_report_hour:
        return None
    iso_year, iso_week, _ = now_local.isocalendar()
    event_key = f"weekly_report:{iso_year}-{iso_week:02d}"
    if _ever_sent(session, event_key):
        return None
    summary = weekly_summary(session, settings)
    if not summary.get("ready"):
        return None
    tires = summary.get("tires")
    tire_text = ""
    if isinstance(tires, dict):
        tire_text = (
            "\nTires: "
            f"FL {tires.get('front_driver_tire') or '—'} · "
            f"FR {tires.get('front_passenger_tire') or '—'} · "
            f"RL {tires.get('rear_driver_tire') or '—'} · "
            f"RR {tires.get('rear_passenger_tire') or '—'}"
        )
    message = (
        f"📊 **{settings.vehicle_display_name} weekly report**\n"
        f"Distance: {summary['distance_km']} km · Trips: {summary['trip_count']}\n"
        f"Average trip: {summary['average_trip_km']} km · "
        f"Longest: {summary['longest_trip_km']} km\n"
        f"Fuel spend: ${summary['fuel_spend']:.2f} · {summary['fuel_liters']} L"
        f"{tire_text}"
    )
    if not await _post_webhook(settings, message):
        return None
    _log_notification(session, event_key, message)
    return message
