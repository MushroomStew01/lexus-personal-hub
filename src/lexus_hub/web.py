from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from html import escape
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .analytics import daily_distance, recent_fuel_fills, recent_trips, status_summary
from .config import get_settings
from .db import init_db, session_scope
from .poller import poll_forever, poll_once
from .providers import get_provider
from .storage import add_fuel_fill, primary_vehicle


class FuelFillRequest(BaseModel):
    liters: float = Field(gt=0, le=200)
    total_cost: float = Field(gt=0, le=2000)
    odometer_km: float | None = Field(default=None, ge=0)
    station: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=250)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    task = asyncio.create_task(poll_forever(get_settings()))
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="Lexus Personal Hub", version="0.3.0", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/poll")
async def api_poll() -> dict[str, Any]:
    try:
        return await poll_once(get_settings())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/status")
def api_status() -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return status_summary(session, settings)


@app.get("/api/provider/test")
async def provider_test() -> dict[str, object]:
    provider = get_provider(get_settings())
    try:
        reading = await provider.fetch()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "provider": provider.name,
        "vehicle": reading.display_name,
        "observed_at": reading.observed_at,
        "odometer_km": reading.odometer_km,
        "fuel_percent": reading.fuel_percent,
        "range_km": reading.range_km,
        "speed_kph": reading.speed_kph,
        "status": reading.raw.get("status", {}),
    }


@app.get("/api/provider/discover")
async def provider_discover() -> dict[str, Any]:
    provider = get_provider(get_settings())
    try:
        return await provider.discover()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/trips")
def api_trips(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict[str, object]]:
    settings = get_settings()
    with session_scope() as session:
        return recent_trips(session, settings, limit)


@app.get("/api/distance")
def api_distance(
    days: Annotated[int, Query(ge=1, le=366)] = 30,
) -> list[dict[str, object]]:
    settings = get_settings()
    with session_scope() as session:
        return daily_distance(session, settings, days)


@app.get("/api/fuel")
def api_fuel(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict[str, object]]:
    settings = get_settings()
    with session_scope() as session:
        return recent_fuel_fills(session, settings, limit)


@app.post("/api/fuel", status_code=201)
def api_add_fuel(payload: FuelFillRequest) -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        vehicle = primary_vehicle(session, settings)
        if vehicle is None:
            raise HTTPException(status_code=409, detail="Poll the vehicle before logging fuel.")
        fill = add_fuel_fill(session, vehicle, **payload.model_dump())
        return {"id": fill.id, "liters": fill.liters, "total_cost": fill.total_cost}


def _fmt(value: object, suffix: str = "", decimals: int = 1) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        return f"{float(value):,.{decimals}f}{suffix}"
    return str(value)


def _pretty_time(value: object) -> str:
    if not value:
        return "—"
    text = str(value).replace("T", " ")
    return text[:19]


def _status_record(
    vehicle_status: dict[str, object],
    key: str,
) -> dict[str, object]:
    record = vehicle_status.get(key)
    return record if isinstance(record, dict) else {}


def _status_display(
    vehicle_status: dict[str, object],
    key: str,
) -> str:
    record = _status_record(vehicle_status, key)
    return str(record.get("display") or record.get("value") or "—")


def _state_class(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"closed", "locked", "off"}:
        return "good"
    if normalized in {"open", "unlocked", "running"}:
        return "bad"
    return "neutral"


def _metric(label: str, value: str, hint: str = "") -> str:
    hint_html = f"<span class='hint'>{escape(hint)}</span>" if hint else ""
    return (
        "<article class='metric'>"
        f"<span class='eyebrow'>{escape(label)}</span>"
        f"<strong>{escape(value)}</strong>{hint_html}"
        "</article>"
    )


def _status_item(
    vehicle_status: dict[str, object],
    label: str,
    key: str,
) -> str:
    value = _status_display(vehicle_status, key)
    return (
        "<div class='status-row'>"
        f"<span>{escape(label)}</span>"
        f"<span class='pill {_state_class(value)}'>{escape(value)}</span>"
        "</div>"
    )


def _tire_card(
    vehicle_status: dict[str, object],
    label: str,
    key: str,
    low_tire_psi: float,
) -> str:
    record = _status_record(vehicle_status, key)
    raw_value = record.get("value")
    warning = isinstance(raw_value, (int, float)) and float(raw_value) < low_tire_psi
    display = str(record.get("display") or "—")
    cls = "tire warning" if warning else "tire"
    return (
        f"<div class='{cls}'>"
        f"<span>{escape(label)}</span>"
        f"<strong>{escape(display)}</strong>"
        "</div>"
    )


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        status = status_summary(session, settings)
        trips = recent_trips(session, settings, limit=6)
        fills = recent_fuel_fills(session, settings, limit=6)
        series = daily_distance(session, settings, days=14)

    vehicle_status_obj = status.get("vehicle_status")
    vehicle_status = vehicle_status_obj if isinstance(vehicle_status_obj, dict) else {}
    ready = bool(status.get("ready"))

    metrics = "".join(
        [
            _metric("Odometer", _fmt(status.get("odometer_km"), " km", 0)),
            _metric("Fuel", _fmt(status.get("fuel_percent"), "%", 0)),
            _metric("Range", _fmt(status.get("range_km"), " km", 0)),
            _metric("Speed", _fmt(status.get("speed_kph"), " km/h", 0)),
            _metric("7-day distance", _fmt(status.get("distance_7d_km"), " km")),
            _metric("30-day distance", _fmt(status.get("distance_30d_km"), " km")),
        ]
    )

    tire_html = "".join(
        [
            _tire_card(vehicle_status, "Front driver", "front_driver_tire", settings.low_tire_psi),
            _tire_card(
                vehicle_status,
                "Front passenger",
                "front_passenger_tire",
                settings.low_tire_psi,
            ),
            _tire_card(vehicle_status, "Rear driver", "rear_driver_tire", settings.low_tire_psi),
            _tire_card(
                vehicle_status,
                "Rear passenger",
                "rear_passenger_tire",
                settings.low_tire_psi,
            ),
        ]
    )

    openings = [
        ("Front driver door", "front_driver_door"),
        ("Front passenger door", "front_passenger_door"),
        ("Rear driver door", "rear_driver_door"),
        ("Rear passenger door", "rear_passenger_door"),
        ("Trunk", "trunk"),
        ("Hood", "hood"),
    ]
    windows = [
        ("Front driver window", "front_driver_window"),
        ("Front passenger window", "front_passenger_window"),
        ("Rear driver window", "rear_driver_window"),
        ("Rear passenger window", "rear_passenger_window"),
        ("Moonroof", "moonroof"),
    ]
    locks = [
        ("Front driver lock", "front_driver_door_lock"),
        ("Front passenger lock", "front_passenger_door_lock"),
        ("Rear driver lock", "rear_driver_door_lock"),
        ("Rear passenger lock", "rear_passenger_door_lock"),
        ("Trunk lock", "trunk_door_lock"),
    ]
    opening_html = "".join(_status_item(vehicle_status, label, key) for label, key in openings)
    window_html = "".join(_status_item(vehicle_status, label, key) for label, key in windows)
    lock_html = "".join(_status_item(vehicle_status, label, key) for label, key in locks)

    max_distance = max((float(item.get("distance_km") or 0) for item in series), default=0.0)
    chart_bars = []
    for item in series:
        distance = float(item.get("distance_km") or 0)
        height = 8 if max_distance <= 0 else max(8, round(distance / max_distance * 100))
        date = str(item.get("date") or "")
        chart_bars.append(
            "<div class='bar-wrap' title='"
            + escape(f"{date}: {distance:.1f} km")
            + "'><div class='bar' style='height:"
            + str(height)
            + "%'></div><span>"
            + escape(date[-5:])
            + "</span></div>"
        )
    chart_html = "".join(chart_bars)

    if trips:
        trip_rows = "".join(
            "<tr>"
            f"<td>{escape(_pretty_time(item.get('started_at')))}</td>"
            f"<td>{escape(_pretty_time(item.get('ended_at')))}</td>"
            f"<td>{escape(_fmt(item.get('distance_km'), ' km'))}</td>"
            f"<td>{'Active' if item.get('is_open') else 'Complete'}</td>"
            "</tr>"
            for item in trips
        )
    else:
        trip_rows = "<tr><td colspan='4' class='empty'>No trips detected yet.</td></tr>"

    if fills:
        fuel_rows = "".join(
            "<tr>"
            f"<td>{escape(_pretty_time(item.get('filled_at')))}</td>"
            f"<td>{escape(_fmt(item.get('liters'), ' L'))}</td>"
            f"<td>${escape(_fmt(item.get('total_cost'), '', 2))}</td>"
            f"<td>{escape(str(item.get('station') or '—'))}</td>"
            "</tr>"
            for item in fills
        )
    else:
        fuel_rows = "<tr><td colspan='4' class='empty'>No fuel fill-ups logged yet.</td></tr>"

    maintenance_items = [
        (
            "Service remaining",
            _fmt(status.get("service_remaining_km"), " km", 0)
            if status.get("service_remaining_km") is not None
            else "Not configured",
        ),
        ("Home Assistant update", _status_display(vehicle_status, "last_update")),
        (
            "Tire pressure update",
            _status_display(vehicle_status, "last_tire_pressure_update"),
        ),
        ("Next service sensor", _status_display(vehicle_status, "next_service")),
        ("Last stored snapshot", _pretty_time(status.get("last_poll"))),
        ("Source updated", _pretty_time(status.get("source_updated_at"))),
    ]
    maintenance_html = "".join(
        "<div class='status-row'><span>"
        + escape(label)
        + "</span><span class='plain-value'>"
        + escape(value)
        + "</span></div>"
        for label, value in maintenance_items
    )

    connection_class = "connected" if ready else "offline"
    connection_text = "Connected via Home Assistant" if ready else "Waiting for telemetry"
    notice = (
        ""
        if ready
        else "<div class='notice'>No saved snapshot yet. Run <code>lexus-hub poll-once</code>.</div>"
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{settings.dashboard_refresh_seconds}">
<title>{escape(settings.vehicle_display_name)} · Lexus Personal Hub</title>
<style>
:root{{--bg:#090d12;--panel:#111820;--panel2:#151e28;--line:#283442;--text:#f6f7f9;
--muted:#8ea0b2;--accent:#d8dde5;--good:#47d18c;--bad:#ff6b6b;--warn:#ffcc66}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at top right,#172331 0,
#090d12 35%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,
Segoe UI,sans-serif}}a{{color:#8ecbff;text-decoration:none}}code{{background:#202b36;padding:2px 6px;
border-radius:6px}}main{{max-width:1280px;margin:auto;padding:34px 22px 70px}}
header{{display:flex;justify-content:space-between;gap:20px;align-items:flex-end;margin-bottom:22px}}
h1{{font-size:2.4rem;margin:2px 0 4px}}h2{{font-size:1.05rem;margin:0 0 16px}}
.kicker,.eyebrow{{color:var(--muted);font-size:.75rem;text-transform:uppercase;
letter-spacing:.09em}}.connection{{display:flex;align-items:center;gap:8px;color:var(--muted);
font-size:.88rem}}.dot{{width:9px;height:9px;border-radius:50%}}.connected .dot{{background:var(--good);
box-shadow:0 0 14px var(--good)}}.offline .dot{{background:var(--bad)}}
.grid{{display:grid;gap:14px}}.metrics{{grid-template-columns:repeat(6,minmax(140px,1fr))}}
.metric,.panel{{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);
border-radius:18px;box-shadow:0 18px 45px rgba(0,0,0,.16)}}.metric{{padding:18px}}
.metric strong{{display:block;font-size:1.55rem;margin-top:9px}}.hint{{display:block;color:var(--muted);
font-size:.75rem;margin-top:8px}}.section-grid{{grid-template-columns:1.05fr 1fr 1fr;margin-top:14px}}
.panel{{padding:20px;min-width:0}}.status-row{{display:flex;justify-content:space-between;gap:16px;
align-items:center;padding:10px 0;border-bottom:1px solid rgba(142,160,178,.12)}}
.status-row:last-child{{border-bottom:0}}.status-row>span:first-child{{color:#c7d0da;font-size:.9rem}}
.pill{{font-size:.76rem;font-weight:700;padding:5px 9px;border-radius:999px;border:1px solid var(--line)}}
.pill.good{{color:var(--good);background:rgba(71,209,140,.08)}}.pill.bad{{color:var(--bad);
background:rgba(255,107,107,.08)}}.pill.neutral{{color:var(--muted)}}.plain-value{{font-size:.8rem;
color:var(--muted);text-align:right}}.tires{{grid-template-columns:repeat(4,1fr)}}.tire{{background:#0d141b;
border:1px solid var(--line);border-radius:14px;padding:14px;text-align:center}}.tire span{{display:block;
color:var(--muted);font-size:.75rem}}.tire strong{{display:block;margin-top:8px;font-size:1.15rem}}
.tire.warning{{border-color:rgba(255,107,107,.7)}}.tire.warning strong{{color:var(--bad)}}
.wide{{margin-top:14px;grid-template-columns:1.25fr .75fr}}.chart{{height:190px;display:flex;align-items:flex-end;
gap:6px;padding-top:18px}}.bar-wrap{{height:100%;flex:1;display:flex;flex-direction:column;justify-content:flex-end;
align-items:center;gap:7px;min-width:0}}.bar{{width:100%;max-width:28px;min-height:5px;
background:linear-gradient(180deg,#a7d7ff,#4b87bd);border-radius:8px 8px 3px 3px}}
.bar-wrap span{{font-size:.58rem;color:var(--muted);transform:rotate(-45deg);white-space:nowrap}}
.table-grid{{grid-template-columns:1fr 1fr;margin-top:14px}}table{{width:100%;border-collapse:collapse;
font-size:.82rem}}th{{color:var(--muted);font-weight:600;text-align:left;padding:8px 6px;
border-bottom:1px solid var(--line)}}td{{padding:10px 6px;border-bottom:1px solid rgba(142,160,178,.1)}}
.empty{{color:var(--muted);text-align:center;padding:24px}}.notice{{padding:12px 14px;border:1px solid #6d5a2f;
background:#2b2414;border-radius:12px;margin-bottom:14px;color:#ffe3a3}}
.links{{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:.85rem;margin-top:20px}}
@media(max-width:1000px){{.metrics{{grid-template-columns:repeat(3,1fr)}}.section-grid{{grid-template-columns:1fr 1fr}}
.section-grid .panel:first-child{{grid-column:1/-1}}.wide,.table-grid{{grid-template-columns:1fr}}}}
@media(max-width:620px){{main{{padding:24px 14px 50px}}header{{align-items:flex-start;flex-direction:column}}
h1{{font-size:2rem}}.metrics{{grid-template-columns:repeat(2,1fr)}}.section-grid{{grid-template-columns:1fr}}
.section-grid .panel:first-child{{grid-column:auto}}.tires{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body><main>
<header>
<div><div class="kicker">Lexus Personal Hub · v0.3</div><h1>{escape(settings.vehicle_display_name)}</h1>
<div class="connection {connection_class}"><span class="dot"></span>{escape(connection_text)}</div></div>
<div class="connection">Local time zone: {escape(settings.timezone)}</div>
</header>
{notice}
<section class="grid metrics">{metrics}</section>

<section class="grid section-grid">
<article class="panel"><h2>Tire pressure</h2><div class="grid tires">{tire_html}</div></article>
<article class="panel"><h2>Doors & body</h2>{opening_html}</article>
<article class="panel"><h2>Windows & locks</h2>{window_html}{lock_html}</article>
</section>

<section class="grid wide">
<article class="panel"><h2>14-day distance</h2><div class="chart">{chart_html}</div></article>
<article class="panel"><h2>Vehicle & maintenance</h2>{maintenance_html}</article>
</section>

<section class="grid table-grid">
<article class="panel"><h2>Recent trips</h2>
<table><thead><tr><th>Start</th><th>End</th><th>Distance</th><th>Status</th></tr></thead>
<tbody>{trip_rows}</tbody></table></article>
<article class="panel"><h2>Fuel history</h2>
<table><thead><tr><th>Date</th><th>Litres</th><th>Cost</th><th>Station</th></tr></thead>
<tbody>{fuel_rows}</tbody></table></article>
</section>

<div class="links">
<a href="/docs">API docs</a><a href="/api/status">Status JSON</a>
<a href="/api/provider/discover">Provider discovery</a><a href="/api/provider/test">Provider test</a>
</div>
</main></body></html>"""
    return HTMLResponse(html)
