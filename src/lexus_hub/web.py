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


app = FastAPI(title="Lexus Personal Hub", version="0.2.0", lifespan=lifespan)


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


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        status = status_summary(session, settings)

    def fmt(value: object, suffix: str = "") -> str:
        if value is None:
            return "—"
        if isinstance(value, (int, float)):
            return f"{value:,.1f}{suffix}"
        return escape(str(value))

    cards = [
        ("Odometer", fmt(status.get("odometer_km"), " km")),
        ("Fuel", fmt(status.get("fuel_percent"), "%")),
        ("Range", fmt(status.get("range_km"), " km")),
        ("7-day distance", fmt(status.get("distance_7d_km"), " km")),
        ("30-day distance", fmt(status.get("distance_30d_km"), " km")),
    ]
    card_html = "".join(
        f"<article><small>{escape(label)}</small><strong>{escape(value)}</strong></article>"
        for label, value in cards
    )
    notice = "" if status.get("ready") else "<p>Waiting for the first saved snapshot.</p>"
    html = (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
        "content='width=device-width,initial-scale=1'><title>Lexus Personal Hub</title><style>"
        "body{font-family:system-ui;background:#0d1117;color:#f0f3f6;margin:0}"
        "main{max-width:1000px;margin:auto;padding:40px 22px}.grid{display:grid;"
        "grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}"
        "article{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:18px}"
        "small{color:#9da7b3}strong{display:block;font-size:1.6rem;margin-top:8px}"
        "a{color:#79c0ff}</style></head><body><main>"
        f"<h1>{escape(settings.vehicle_display_name)}</h1>{notice}<div class='grid'>{card_html}</div>"
        "<p><a href='/docs'>API docs</a> · <a href='/api/provider/discover'>Provider discovery</a>"
        " · <a href='/api/provider/test'>Provider test</a></p></main></body></html>"
    )
    return HTMLResponse(html)
