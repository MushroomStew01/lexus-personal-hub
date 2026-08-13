from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from .config import get_settings
from .providers import get_provider

app = FastAPI(title="Lexus Personal Hub", version="0.2.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
async def status() -> dict[str, Any]:
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
