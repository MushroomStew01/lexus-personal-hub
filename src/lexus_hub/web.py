from __future__ import annotations

from html import escape
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .config import get_settings
from .providers import get_provider

app = FastAPI(title="Lexus Personal Hub", version="0.2.0")


def _fmt(value: float | None, suffix: str) -> str:
    return "—" if value is None else f"{value:,.1f}{suffix}"


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


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    provider = get_provider(get_settings())
    try:
        reading = await provider.fetch()
        cards = [
            ("Odometer", _fmt(reading.odometer_km, " km")),
            ("Fuel", _fmt(reading.fuel_percent, "%")),
            ("Range", _fmt(reading.range_km, " km")),
            ("Speed", _fmt(reading.speed_kph, " km/h")),
        ]
        body = "".join(
            f'<article><small>{escape(label)}</small><strong>{escape(value)}</strong></article>'
            for label, value in cards
        )
        message = ""
    except Exception as exc:
        body = ""
        message = f'<p class="error">{escape(str(exc))}</p>'

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lexus Personal Hub</title>
<style>
body{{font-family:system-ui;margin:0;background:#0d1117;color:#f0f3f6}}
main{{max-width:980px;margin:auto;padding:40px 22px}}
h1{{margin-bottom:4px}}p{{color:#9da7b3}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}}
article{{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:20px}}
small{{display:block;color:#8b949e;text-transform:uppercase}}
strong{{display:block;font-size:1.8rem;margin-top:8px}}
.error{{padding:14px;border:1px solid #6e3b3b;border-radius:10px;color:#ffb4b4}}
a{{color:#79c0ff}}
</style>
</head>
<body><main>
<h1>Lexus Personal Hub</h1>
<p>Read-only current telemetry via {escape(provider.name)}.</p>
{message}<div class="grid">{body}</div>
<p><a href="/docs">API docs</a> · <a href="/api/provider/discover">Provider discovery</a></p>
</main></body></html>"""
    return HTMLResponse(html)
