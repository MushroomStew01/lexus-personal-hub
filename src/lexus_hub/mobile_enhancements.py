from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .db import init_db, session_scope
from .insights import location_label
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


def _address_from_geoapify(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        return None
    for key in ("formatted", "address_line1"):
        value = first.get(key)
        if isinstance(value, str) and value.strip():
            if key == "address_line1":
                line2 = first.get("address_line2")
                if isinstance(line2, str) and line2.strip():
                    return f"{value.strip()}, {line2.strip()}"
            return value.strip()
    return None


@lru_cache(maxsize=512)
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


def _estimated_address(latitude: float | None, longitude: float | None) -> str | None:
    settings = get_settings()
    if latitude is None or longitude is None or not settings.geoapify_api_key:
        return None
    # About 11 m of latitude precision. This keeps repeated parking samples from
    # generating needless reverse-geocoding requests while preserving useful addresses.
    return _reverse_geocode_geoapify(
        round(float(latitude), 4),
        round(float(longitude), 4),
        settings.geoapify_api_key,
    )


def _trip_snapshots(vehicle_id: int, trip: Trip) -> list[Snapshot]:
    replay_end = trip.ended_at or trip.last_movement_at
    with session_scope() as session:
        return list(
            session.scalars(
                select(Snapshot)
                .where(
                    Snapshot.vehicle_id == vehicle_id,
                    Snapshot.observed_at >= trip.started_at,
                    Snapshot.observed_at <= replay_end,
                )
                .order_by(Snapshot.observed_at.asc())
            ).all()
        )


def _trip_metrics(snapshots: list[Snapshot], trip: Trip) -> dict[str, object]:
    duration_seconds = max(
        0.0,
        ((trip.ended_at or trip.last_movement_at) - trip.started_at).total_seconds(),
    )
    duration_minutes = round(duration_seconds / 60.0)

    speeds = [float(row.speed_kph) for row in snapshots if row.speed_kph is not None]
    top_speed = round(max(speeds), 1) if speeds else None
    average_speed = (
        round(float(trip.distance_km) / (duration_seconds / 3600.0), 1)
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

    settings = get_settings()
    fuel_used_liters = None
    if fuel_drop is not None and settings.fuel_tank_capacity_liters is not None:
        fuel_used_liters = round(settings.fuel_tank_capacity_liters * fuel_drop / 100.0, 2)

    ranges = [float(row.range_km) for row in snapshots if row.range_km is not None]
    range_start = ranges[0] if ranges else None
    range_end = ranges[-1] if ranges else None

    return {
        "duration_minutes": duration_minutes,
        "top_speed_kph": top_speed,
        "average_speed_kph": average_speed,
        "fuel_start_percent": fuel_start,
        "fuel_end_percent": fuel_end,
        "fuel_drop_percent": fuel_drop,
        "fuel_used_liters_estimate": fuel_used_liters,
        "range_start_km": range_start,
        "range_end_km": range_end,
        "start_odometer_km": round(float(trip.start_odometer_km), 1),
        "end_odometer_km": round(float(trip.end_odometer_km), 1),
        "telemetry_samples": len(snapshots),
        "speed_note": "Top speed is the highest saved telemetry sample, not guaranteed trip maximum.",
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
        start_label = location_label(
            session,
            vehicle.id,
            trip.start_latitude,
            trip.start_longitude,
            reveal_private_name=False,
            reveal_coordinates=False,
        )
        end_label = location_label(
            session,
            vehicle.id,
            trip.end_latitude,
            trip.end_longitude,
            reveal_private_name=False,
            reveal_coordinates=False,
        )
        vehicle_id = vehicle.id
        start_latitude = trip.start_latitude
        start_longitude = trip.start_longitude
        end_latitude = trip.end_latitude
        end_longitude = trip.end_longitude
        trip_copy = Trip(
            id=trip.id,
            vehicle_id=trip.vehicle_id,
            started_at=trip.started_at,
            ended_at=trip.ended_at,
            last_movement_at=trip.last_movement_at,
            start_odometer_km=trip.start_odometer_km,
            end_odometer_km=trip.end_odometer_km,
            distance_km=trip.distance_km,
            start_latitude=trip.start_latitude,
            start_longitude=trip.start_longitude,
            end_latitude=trip.end_latitude,
            end_longitude=trip.end_longitude,
            is_open=trip.is_open,
        )

    snapshots = _trip_snapshots(vehicle_id, trip_copy)
    start_address = None if start_label != "Unnamed location" else _estimated_address(start_latitude, start_longitude)
    end_address = None if end_label != "Unnamed location" else _estimated_address(end_latitude, end_longitude)
    return {
        "id": trip_id,
        "start_label": start_label,
        "end_label": end_label,
        "start_address": start_address,
        "end_address": end_address,
        "metrics": _trip_metrics(snapshots, trip_copy),
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
        label = location_label(
            session,
            vehicle.id,
            latest.latitude,
            latest.longitude,
            reveal_private_name=False,
            reveal_coordinates=False,
        )
        latitude = latest.latitude
        longitude = latest.longitude
        speed = latest.speed_kph

    # Never send a named/private location to an external reverse-geocoder. Only
    # estimate an address for an otherwise unnamed parked location.
    address = None
    parked = speed is None or speed <= settings.parking_speed_threshold_kph
    if label == "Unnamed location" and parked:
        address = _estimated_address(latitude, longitude)
    return {
        "ready": True,
        "label": label,
        "estimated_address": address,
        "geocoder_configured": bool(settings.geoapify_api_key),
    }


@router.get("/api/access")
def api_access(request: Request) -> dict[str, object]:
    settings = get_settings()
    current_origin = f"{request.url.scheme}://{request.url.netloc}"
    return {
        "current_origin": current_origin,
        "local_url": settings.local_dashboard_url,
        "remote_url": settings.dashboard_url,
        "local_origin": _safe_origin(settings.local_dashboard_url),
        "remote_origin": _safe_origin(settings.dashboard_url),
        "mode": "local" if current_origin == _safe_origin(settings.local_dashboard_url) else "private_remote",
        "automatic_local_switch": False,
        "note": "iOS secure PWAs cannot reliably probe an HTTP LAN origin from an HTTPS app; use the Local button or split-DNS/local HTTPS for transparent switching.",
    }


@router.get("/mobile-enhancements.js", include_in_schema=False)
def mobile_enhancements_js() -> Response:
    script = r"""
(() => {
  const getJSON = async url => {
    const response = await fetch(url, {cache: 'no-store'});
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  };

  const style = document.createElement('style');
  style.textContent = `
    .trip-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px}
    .trip-stat{background:#0d141b;border:1px solid #283442;border-radius:10px;padding:8px}
    .trip-stat span{display:block;color:#8ea0b2;font-size:.62rem;text-transform:uppercase;letter-spacing:.05em}
    .trip-stat strong{display:block;margin-top:3px;font-size:.78rem}
    .connection-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
    .connection-actions a{display:inline-block;border:1px solid #38516a;background:#162535;color:#a9d8ff;
      border-radius:10px;padding:8px 10px;text-decoration:none;font-size:.78rem}
    .safe-note{color:#8ea0b2;font-size:.7rem;line-height:1.4;margin-top:8px}
    @media(max-width:420px){.trip-stats{grid-template-columns:repeat(2,1fr)}}
  `;
  document.head.appendChild(style);

  const fmt = (value, suffix='') => value === null || value === undefined ? '—' : `${value}${suffix}`;

  async function enhanceLocation() {
    try {
      const data = await getJSON('/api/location/address');
      if (!data.ready || !data.estimated_address) return;
      const main = document.querySelector('#where-main');
      if (main && ['Unnamed location', 'Unknown location'].includes(main.textContent.trim())) {
        main.textContent = data.estimated_address;
      }
    } catch (_) {}
  }

  async function enhanceTrips() {
    try {
      const trips = await getJSON('/api/trips?limit=4');
      const rows = [...document.querySelectorAll('#trips .trip')];
      await Promise.all(trips.slice(0, rows.length).map(async (trip, index) => {
        const row = rows[index];
        const details = await getJSON(`/api/trips/${trip.id}/details`);
        const route = row.querySelector('.trip-route');
        if (route) {
          const start = details.start_address || details.start_label || trip.start_label || 'Start';
          const end = details.end_address || details.end_label || trip.end_label || 'End';
          route.textContent = `${start} → ${end}`;
        }
        const metrics = details.metrics || {};
        const stats = document.createElement('div');
        stats.className = 'trip-stats';
        const items = [
          ['Duration', fmt(metrics.duration_minutes, ' min')],
          ['Top speed*', fmt(metrics.top_speed_kph, ' km/h')],
          ['Avg speed', fmt(metrics.average_speed_kph, ' km/h')],
          ['Fuel drop', fmt(metrics.fuel_drop_percent, '%')],
          ['Fuel used', metrics.fuel_used_liters_estimate == null ? 'Set tank size' : fmt(metrics.fuel_used_liters_estimate, ' L')],
          ['Samples', fmt(metrics.telemetry_samples)],
        ];
        items.forEach(([label, value]) => {
          const item = document.createElement('div');
          item.className = 'trip-stat';
          const name = document.createElement('span');
          name.textContent = label;
          const val = document.createElement('strong');
          val.textContent = value;
          item.append(name, val);
          stats.appendChild(item);
        });
        row.appendChild(stats);
      }));
      if (rows.length) {
        const note = document.createElement('div');
        note.className = 'safe-note';
        note.textContent = '* Top speed is the highest saved telemetry sample, so a brief peak between polls may be missed.';
        document.querySelector('#trips')?.appendChild(note);
      }
    } catch (_) {}
  }

  async function enhanceAccess() {
    try {
      const access = await getJSON('/api/access');
      const grid = document.querySelector('section.grid');
      if (!grid) return;
      const card = document.createElement('article');
      card.className = 'card';
      const heading = document.createElement('h2');
      heading.textContent = 'Connection';
      const main = document.createElement('div');
      main.className = 'where-main';
      main.textContent = access.mode === 'local' ? 'Home LAN' : 'Tailscale / private';
      const detail = document.createElement('div');
      detail.className = 'sub';
      detail.textContent = access.current_origin || 'Current connection';
      card.append(heading, main, detail);
      const actions = document.createElement('div');
      actions.className = 'connection-actions';
      if (access.local_url) {
        const local = document.createElement('a');
        local.href = access.local_url;
        local.textContent = 'Use Home LAN';
        actions.appendChild(local);
      }
      if (access.remote_url && access.remote_url !== access.local_url) {
        const remote = document.createElement('a');
        remote.href = access.remote_url;
        remote.textContent = 'Use Tailscale';
        actions.appendChild(remote);
      }
      if (actions.children.length) card.appendChild(actions);
      const note = document.createElement('div');
      note.className = 'safe-note';
      note.textContent = 'Transparent LAN switching needs split-DNS/local HTTPS. The buttons let you choose the path without changing app data.';
      card.appendChild(note);
      grid.appendChild(card);
    } catch (_) {}
  }

  async function run() {
    // Let the base PWA populate its cards first.
    await new Promise(resolve => setTimeout(resolve, 500));
    await Promise.all([enhanceLocation(), enhanceTrips(), enhanceAccess()]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run, {once: true});
  } else {
    run();
  }
})();
""".strip()
    return Response(content=script, media_type="application/javascript", headers={"Cache-Control": "no-cache"})


class MobileEnhancementMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path != "/app" or "text/html" not in response.headers.get("content-type", ""):
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
