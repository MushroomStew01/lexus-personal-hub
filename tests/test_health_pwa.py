import json
from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from lexus_hub.config import Settings
from lexus_hub.db import Base
from lexus_hub.health import vehicle_health_score
from lexus_hub.models import Snapshot, Vehicle
from lexus_hub.pwa import router as pwa_router
from lexus_hub.timeutil import utcnow


def _healthy_status() -> dict[str, object]:
    status: dict[str, object] = {}
    for key in (
        "front_driver_tire",
        "front_passenger_tire",
        "rear_driver_tire",
        "rear_passenger_tire",
    ):
        status[key] = {"value": 38.0, "display": "38 psi"}
    for key in (
        "front_driver_door",
        "front_passenger_door",
        "rear_driver_door",
        "rear_passenger_door",
        "front_driver_window",
        "front_passenger_window",
        "rear_driver_window",
        "rear_passenger_window",
        "moonroof",
        "hood",
        "trunk",
    ):
        status[key] = {"value": "Closed", "display": "Closed"}
    for key in (
        "front_driver_door_lock",
        "front_passenger_door_lock",
        "rear_driver_door_lock",
        "rear_passenger_door_lock",
        "trunk_door_lock",
    ):
        status[key] = {"value": "Locked", "display": "Locked"}
    status["next_service"] = {"value": 1500.0, "display": "1500 km"}
    return status


def test_vehicle_health_score_is_healthy_with_good_telemetry():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(_env_file=None, provider="mock", low_tire_psi=30)
    now = utcnow()

    with Session(engine) as session:
        vehicle = Vehicle(
            provider="mock",
            provider_vehicle_id="mock:primary",
            display_name="Test Lexus",
        )
        session.add(vehicle)
        session.flush()
        session.add(
            Snapshot(
                vehicle_id=vehicle.id,
                observed_at=now,
                source_updated_at=now - timedelta(minutes=5),
                odometer_km=1000,
                fuel_percent=80,
                range_km=400,
                speed_kph=0,
                raw_json=json.dumps({"status": _healthy_status()}),
            )
        )
        session.flush()

        result = vehicle_health_score(session, settings)
        assert result["ready"] is True
        assert result["score"] == 100
        assert result["grade"] == "Excellent"
        assert result["attention_count"] == 0


def test_vehicle_health_score_penalizes_critical_tire():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(_env_file=None, provider="mock", low_tire_psi=30)
    now = utcnow()
    status = _healthy_status()
    status["front_driver_tire"] = {"value": 20.0, "display": "20 psi"}

    with Session(engine) as session:
        vehicle = Vehicle(
            provider="mock",
            provider_vehicle_id="mock:primary",
            display_name="Test Lexus",
        )
        session.add(vehicle)
        session.flush()
        session.add(
            Snapshot(
                vehicle_id=vehicle.id,
                observed_at=now,
                source_updated_at=now,
                odometer_km=1000,
                fuel_percent=80,
                range_km=400,
                speed_kph=0,
                raw_json=json.dumps({"status": status}),
            )
        )
        session.flush()

        result = vehicle_health_score(session, settings)
        assert result["score"] == 88
        tires = next(check for check in result["checks"] if check["name"] == "Tires")
        assert tires["state"] == "alert"
        assert tires["deduction"] == 12


def test_pwa_shell_routes_are_installable_resources():
    app = FastAPI()
    app.include_router(pwa_router)
    client = TestClient(app)

    page = client.get("/app")
    assert page.status_code == 200
    assert 'rel="manifest" href="/manifest.webmanifest"' in page.text
    assert "navigator.serviceWorker.register('/sw.js')" in page.text

    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.json()["display"] == "standalone"
    assert manifest.json()["start_url"] == "/app"

    icon = client.get("/pwa/icon-192.png")
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/png")
    assert icon.content.startswith(b"\x89PNG")

    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert "lexus-hub-shell-v1" in worker.text
    assert "url.pathname.startsWith('/api/')" in worker.text
