from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings, get_settings
from .db import init_db, session_scope
from .models import Snapshot, Trip
from .storage import primary_vehicle

router = APIRouter(tags=["mobile enhancements"])

_ENHANCEMENT_SCRIPT = '<script src="/mobile-enhancements.js"></script>'


def _safe_origin(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _host_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.hostname.lower() if parsed.hostname else None


def _local_iso(value: datetime | None, settings: Settings) -> str | None:
    if value is None:
        return None
    source = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return source.astimezone(ZoneInfo(settings.timezone)).isoformat()


def _address_from_geoapify(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        return None
    formatted = first.get("formatted")
    if isinstance(formatted, str) and formatted.strip():
        return formatted.strip()
    line1 = first.get("address_line1")
    line2 = first.get("address_line2")
    if isinstance(line1, str) and line1.strip():
        if isinstance(line2, str) and line2.strip():
            return f"{line1.strip()}, {line2.strip()}"
        return line1.strip()
    return None


@lru_cache(maxsize=1024)
def _reverse_geocode_geoapify(
    latitude_rounded: float,
    longitude_rounded: float,
    api_key: str,
) -> str | None:
    try:
        response = httpx.get(
            "https://api.geoapify.com/v1/geocode/reverse",
            params={
                "lat": latitude_rounded,
                "lon": longitude_rounded,
                "format": "json",
                "lang": "en",
                "apiKey": api_key,
            },
            timeout=8.0,
            follow_redirects=True,
            headers={"User-Agent": "Lexus-Personal-Hub/0.3"},
        )
        response.raise_for_status()
        return _address_from_geoapify(response.json())
    except (httpx.HTTPError, ValueError, TypeError):
        return None


def _estimated_address(
    settings: Settings,
    latitude: float | None,
    longitude: float | None,
) -> str | None:
    if latitude is None or longitude is None or not settings.geoapify_api_key:
        return None
    return _reverse_geocode_geoapify(
        round(float(latitude), 4),
        round(float(longitude), 4),
        settings.geoapify_api_key,
    )


def _haversine_km(a: Snapshot, b: Snapshot) -> float | None:
    if a.latitude is None or a.longitude is None or b.latitude is None or b.longitude is None:
        return None
    radius_km = 6371.0088
    lat1 = radians(float(a.latitude))
    lat2 = radians(float(b.latitude))
    d_lat = lat2 - lat1
    d_lon = radians(float(b.longitude) - float(a.longitude))
    h = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    return radius_km * 2 * asin(min(1.0, sqrt(h)))


def _segment_speed_estimates(snapshots: list[Snapshot]) -> list[float]:
    """Diagnostic-only coarse segment speeds; never used as the displayed max speed."""
    estimates: list[float] = []
    for previous, current in zip(snapshots, snapshots[1:], strict=False):
        seconds = (current.observed_at - previous.observed_at).total_seconds()
        if seconds <= 0:
            continue
        hours = seconds / 3600.0
        distance_km: float | None = None
        if previous.odometer_km is not None and current.odometer_km is not None:
            delta = float(current.odometer_km) - float(previous.odometer_km)
            if 0 < delta <= 50:
                distance_km = delta
        if distance_km is None:
            distance_km = _haversine_km(previous, current)
        if distance_km is None or distance_km <= 0:
            continue
        estimate = distance_km / hours
        if 0 < estimate <= 250:
            estimates.append(estimate)
    return estimates


def _fresh_speed_samples(snapshots: list[Snapshot], trip: Trip) -> list[float]:
    """Return de-duplicated Toyota speed samples that belong to this trip.

    Lexus Hub polls Home Assistant more often than Toyota necessarily uploads telemetry. Repeated
    snapshots can therefore contain the same old speed value. A Toyota Last Update timestamp lets us
    collapse those repeats and reject samples whose source timestamp is clearly outside the trip.
    """

    effective_end = trip.ended_at or trip.last_movement_at
    window_start = trip.started_at - timedelta(minutes=10)
    window_end = effective_end + timedelta(minutes=10)
    seen_revisions: set[datetime] = set()
    samples: list[float] = []

    for row in snapshots:
        if row.speed_kph is None:
            continue
        speed = float(row.speed_kph)
        if not 0 <= speed <= 250:
            continue
        source = row.source_updated_at
        if source is not None:
            if source < window_start or source > window_end:
                continue
            if source in seen_revisions:
                continue
            seen_revisions.add(source)
        samples.append(speed)
    return samples


def _trip_metrics(
    snapshots: list[Snapshot],
    trip: Trip,
    settings: Settings,
) -> dict[str, object]:
    effective_end = trip.ended_at or trip.last_movement_at
    duration_seconds = max(0.0, (effective_end - trip.started_at).total_seconds())
    duration_minutes = round(duration_seconds / 60.0)

    speeds = _fresh_speed_samples(snapshots, trip)
    sampled_peak = max(speeds) if speeds else None
    average_speed = (
        float(trip.distance_km) / (duration_seconds / 3600.0)
        if duration_seconds > 0 and trip.distance_km > 0
        else None
    )

    fuels = [float(row.fuel_percent) for row in snapshots if row.fuel_percent is not None]
    fuel_start = fuels[0] if fuels else None
    fuel_end = fuels[-1] if fuels else None
    fuel_drop = (
        round(max(0.0, fuel_start - fuel_end), 1)
        if fuel_start is not None and fuel_end is not None
        else None
    )
    fuel_used_liters = None
    if fuel_drop is not None and settings.fuel_tank_capacity_liters is not None:
        fuel_used_liters = round(settings.fuel_tank_capacity_liters * fuel_drop / 100.0, 2)

    ranges = [float(row.range_km) for row in snapshots if row.range_km is not None]
    range_start = ranges[0] if ranges else None
    range_end = ranges[-1] if ranges else None

    return {
        "duration_minutes": duration_minutes,
        "top_speed_kph": round(sampled_peak, 1) if sampled_peak is not None else None,
        "peak_speed_estimate_kph": round(sampled_peak, 1) if sampled_peak is not None else None,
        "sampled_top_speed_kph": round(sampled_peak, 1) if sampled_peak is not None else None,
        "average_speed_kph": round(average_speed, 1) if average_speed is not None else None,
        "fuel_start_percent": fuel_start,
        "fuel_end_percent": fuel_end,
        "fuel_drop_percent": fuel_drop,
        "fuel_used_liters_estimate": fuel_used_liters,
        "range_start_km": range_start,
        "range_end_km": range_end,
        "start_odometer_km": round(float(trip.start_odometer_km), 1),
        "end_odometer_km": round(float(trip.end_odometer_km), 1),
        "telemetry_samples": len(snapshots),
        "speed_samples": len(speeds),
        "speed_note": (
            "Top speed is the highest fresh Toyota speed sample saved during this trip. "
            "Brief peaks between Toyota telemetry updates can be missed; odometer/GPS segment "
            "averages are intentionally not used as a fake maximum."
        ),
    }


@router.get("/api/trips/{trip_id}/details")
def api_trip_details(trip_id: int) -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        vehicle = primary_vehicle(session, settings)
        if vehicle is None:
            raise HTTPException(status_code=404, detail="Vehicle not found.")
        trip = session.scalar(
            select(Trip).where(Trip.id == trip_id, Trip.vehicle_id == vehicle.id).limit(1)
        )
        if trip is None:
            raise HTTPException(status_code=404, detail="Trip not found.")

        replay_end = trip.ended_at or trip.last_movement_at
        snapshots = list(
            session.scalars(
                select(Snapshot)
                .where(
                    Snapshot.vehicle_id == vehicle.id,
                    Snapshot.observed_at >= trip.started_at,
                    Snapshot.observed_at <= replay_end,
                )
                .order_by(Snapshot.observed_at.asc())
            ).all()
        )
        metrics = _trip_metrics(snapshots, trip, settings)
        start_latitude = trip.start_latitude
        start_longitude = trip.start_longitude
        end_latitude = trip.end_latitude
        end_longitude = trip.end_longitude

    start_address = _estimated_address(settings, start_latitude, start_longitude)
    end_address = _estimated_address(settings, end_latitude, end_longitude)
    return {
        "id": trip_id,
        "start_label": start_address or "Unknown location",
        "end_label": end_address or "Unknown location",
        "start_address": start_address,
        "end_address": end_address,
        "metrics": metrics,
    }


@router.get("/api/location/address")
def api_current_address() -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        vehicle = primary_vehicle(session, settings)
        if vehicle is None:
            return {"ready": False}
        latest = session.scalar(
            select(Snapshot)
            .where(Snapshot.vehicle_id == vehicle.id)
            .order_by(Snapshot.observed_at.desc())
            .limit(1)
        )
        if latest is None:
            return {"ready": False}
        latitude = latest.latitude
        longitude = latest.longitude
        speed = latest.speed_kph

    parked = speed is None or speed <= settings.parking_speed_threshold_kph
    address = _estimated_address(settings, latitude, longitude) if parked else None
    return {
        "ready": True,
        "label": address or ("Physical address unavailable" if parked else "Vehicle moving"),
        "estimated_address": address,
        "parked": parked,
        "geocoder_configured": bool(settings.geoapify_api_key),
    }


@router.get("/api/timeline/physical")
def api_physical_timeline(limit: int = Query(default=20, ge=1, le=50)) -> list[dict[str, object]]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        vehicle = primary_vehicle(session, settings)
        if vehicle is None:
            return []
        trips = list(
            session.scalars(
                select(Trip)
                .where(Trip.vehicle_id == vehicle.id)
                .order_by(Trip.started_at.desc())
                .limit(max(6, min(limit, 20)))
            ).all()
        )
        rows = [
            {
                "started_at": trip.started_at,
                "ended_at": trip.ended_at,
                "distance_km": trip.distance_km,
                "start_latitude": trip.start_latitude,
                "start_longitude": trip.start_longitude,
                "end_latitude": trip.end_latitude,
                "end_longitude": trip.end_longitude,
            }
            for trip in trips
        ]

    events: list[dict[str, object]] = []
    for row in rows:
        start_address = _estimated_address(
            settings,
            row["start_latitude"],
            row["start_longitude"],
        ) or "Unknown location"
        events.append(
            {
                "type": "trip_start",
                "text": f"Trip started from {start_address}",
                "at": _local_iso(row["started_at"], settings),
            }
        )
        if row["ended_at"] is not None:
            end_address = _estimated_address(
                settings,
                row["end_latitude"],
                row["end_longitude"],
            ) or "Unknown location"
            events.append(
                {
                    "type": "trip_end",
                    "text": f"Trip completed at {end_address} · {float(row['distance_km']):.1f} km",
                    "at": _local_iso(row["ended_at"], settings),
                }
            )

    def sort_key(item: dict[str, object]) -> str:
        return str(item.get("at") or "")

    events.sort(key=sort_key, reverse=True)
    return events[:limit]


@router.get("/api/access")
def api_access(request: Request) -> dict[str, object]:
    settings = get_settings()
    host_header = request.headers.get("host", "")
    current_host = host_header.rsplit(":", 1)[0].strip("[]").lower()
    forwarded_proto = request.headers.get("x-forwarded-proto")
    current_scheme = (
        forwarded_proto.split(",", 1)[0].strip() if forwarded_proto else request.url.scheme
    )
    current_origin = (
        f"{current_scheme}://{host_header}"
        if host_header
        else str(request.base_url).rstrip("/")
    )
    local_host = _host_from_url(settings.local_dashboard_url)
    remote_host = _host_from_url(settings.dashboard_url)
    if current_host and local_host and current_host == local_host:
        mode = "local"
    elif current_host and remote_host and current_host == remote_host:
        mode = "private_remote"
    else:
        mode = "private_remote"
    return {
        "current_origin": current_origin,
        "local_url": settings.local_dashboard_url,
        "remote_url": settings.dashboard_url,
        "local_origin": _safe_origin(settings.local_dashboard_url),
        "remote_origin": _safe_origin(settings.dashboard_url),
        "mode": mode,
        "automatic_local_switch": False,
        "note": (
            "iOS secure PWAs cannot reliably probe an HTTP LAN origin from an HTTPS app; "
            "use the Local button or split-DNS/local HTTPS for transparent switching."
        ),
    }


@router.get("/mobile-enhancements.js", include_in_schema=False)
def mobile_enhancements_js() -> Response:
    return Response(
        content="/* Lexus Hub mobile enhancements are integrated into the current app shell. */",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


class MobileEnhancementMiddleware(BaseHTTPMiddleware):
    """Compatibility middleware for old cached shells; current v3 does not require it."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path != "/app" or "text/html" not in response.headers.get(
            "content-type", ""
        ):
            return response
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode("utf-8", errors="replace")
        if _ENHANCEMENT_SCRIPT not in text and "</body>" in text:
            text = text.replace("</body>", f"{_ENHANCEMENT_SCRIPT}\n</body>", 1)
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=text,
            status_code=response.status_code,
            headers=headers,
            media_type="text/html",
        )
