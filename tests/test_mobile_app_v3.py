from fastapi import FastAPI
from fastapi.testclient import TestClient

from lexus_hub.mobile_app_v3 import router


def test_mobile_v3_contains_polished_navigation_and_trip_ui():
    app = FastAPI()
    app.include_router(router)
    page = TestClient(app).get("/app")

    assert page.status_code == 200
    assert "Overview" in page.text
    assert "Tire pressure" in page.text
    assert "Driving trends" in page.text
    assert "Vehicle activity" in page.text
    assert "Sampled peak" in page.text
    assert "Open full replay" in page.text
    assert "/vendor/maplibre-gl.js" in page.text
    assert "Requesting Lexus update" in page.text
    assert "Use Home LAN" in page.text
    assert "Use Tailscale" in page.text


def test_mobile_v3_uses_compact_bottom_navigation():
    app = FastAPI()
    app.include_router(router)
    page = TestClient(app).get("/app")

    assert 'data-tab="overview"' in page.text
    assert 'data-tab="status"' in page.text
    assert 'data-tab="trips"' in page.text
    assert 'href="/garage"' in page.text
