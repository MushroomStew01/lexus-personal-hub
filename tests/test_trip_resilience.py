from datetime import timedelta

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from lexus_hub.config import Settings
from lexus_hub.db import Base
from lexus_hub.models import Trip
from lexus_hub.providers.base import VehicleReading
from lexus_hub.resilience import DashboardMapFallbackMiddleware
from lexus_hub.resilience import router as resilience_router
from lexus_hub.storage import save_snapshot, trip_diagnostics
from lexus_hub.timeutil import utcnow


def _reading(
    at,
    *,
    odometer_km: float = 1000.0,
    speed_kph: float = 0.0,
    latitude: float | None = None,
    longitude: float | None = None,
) -> VehicleReading:
    return VehicleReading(
        provider_vehicle_id="mock:primary",
        display_name="Test Lexus",
        observed_at=at,
        odometer_km=odometer_km,
        speed_kph=speed_kph,
        latitude=latitude,
        longitude=longitude,
    )


def test_gps_movement_can_start_and_close_trip_without_odometer_change():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        store_location=True,
        min_trip_delta_km=0.2,
        trip_idle_close_minutes=30,
    )
    start = utcnow()

    with Session(engine) as session:
        save_snapshot(
            session,
            _reading(start, latitude=43.4516, longitude=-80.4925),
            "mock",
            settings,
        )
        save_snapshot(
            session,
            _reading(
                start + timedelta(minutes=10),
                latitude=43.4566,
                longitude=-80.4925,
            ),
            "mock",
            settings,
        )

        trip = session.scalar(select(Trip))
        assert trip is not None
        assert trip.is_open is True
        assert trip.distance_km == 0.0

        save_snapshot(
            session,
            _reading(
                start + timedelta(minutes=45),
                latitude=43.4566,
                longitude=-80.4925,
            ),
            "mock",
            settings,
        )
        assert trip.is_open is False
        assert trip.ended_at == start + timedelta(minutes=10)


def test_speed_can_start_trip_before_odometer_catches_up():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        min_trip_delta_km=0.2,
        trip_idle_close_minutes=30,
    )
    start = utcnow()

    with Session(engine) as session:
        save_snapshot(session, _reading(start), "mock", settings)
        save_snapshot(
            session,
            _reading(start + timedelta(minutes=5), speed_kph=35),
            "mock",
            settings,
        )

        trip = session.scalar(select(Trip))
        assert trip is not None
        assert trip.is_open is True
        assert trip.distance_km == 0.0


def test_late_odometer_jump_reconciles_recent_gps_trip_instead_of_duplicate():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        store_location=True,
        min_trip_delta_km=0.2,
        trip_idle_close_minutes=30,
        max_snapshot_gap_hours=6,
    )
    start = utcnow()

    with Session(engine) as session:
        save_snapshot(
            session,
            _reading(start, latitude=43.4516, longitude=-80.4925),
            "mock",
            settings,
        )
        save_snapshot(
            session,
            _reading(
                start + timedelta(minutes=10),
                latitude=43.4566,
                longitude=-80.4925,
            ),
            "mock",
            settings,
        )
        save_snapshot(
            session,
            _reading(
                start + timedelta(minutes=45),
                latitude=43.4566,
                longitude=-80.4925,
            ),
            "mock",
            settings,
        )

        trip = session.scalar(select(Trip))
        assert trip is not None
        assert trip.is_open is False
        assert trip.distance_km == 0.0

        save_snapshot(
            session,
            _reading(
                start + timedelta(minutes=60),
                odometer_km=1005.0,
                latitude=43.4566,
                longitude=-80.4925,
            ),
            "mock",
            settings,
        )

        assert session.scalar(select(func.count(Trip.id))) == 1
        assert trip.distance_km == 5.0
        assert trip.end_odometer_km == 1005.0


def test_trip_diagnostics_explain_latest_movement_signal():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(_env_file=None, store_location=True, min_trip_delta_km=0.2)
    start = utcnow()

    with Session(engine) as session:
        save_snapshot(
            session,
            _reading(start, latitude=43.4516, longitude=-80.4925),
            "mock",
            settings,
        )
        save_snapshot(
            session,
            _reading(
                start + timedelta(minutes=10),
                latitude=43.4566,
                longitude=-80.4925,
            ),
            "mock",
            settings,
        )

        result = trip_diagnostics(session, settings)
        assert result["ready"] is True
        assert result["signals"]["gps_moving"] is True
        assert result["signals"]["moving"] is True
        assert result["open_trip_id"] is not None


def test_dashboard_uses_vendored_maplibre_and_keeps_fallback():
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def page() -> HTMLResponse:
        return HTMLResponse(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/'
            'maplibre-gl@6.3.0/dist/maplibre-gl.css">'
            '<script src="https://cdn.jsdelivr.net/npm/'
            'maplibre-gl@6.3.0/dist/maplibre-gl.js"></script>'
            "<script>window.test = true;</script>"
        )

    app.include_router(resilience_router)
    app.add_middleware(DashboardMapFallbackMiddleware)
    client = TestClient(app)

    page_response = client.get("/")
    assert page_response.status_code == 200
    assert '<link rel="stylesheet" href="/vendor/maplibre-gl.css">' in page_response.text
    assert '<script src="/vendor/maplibre-gl.js"></script>' in page_response.text
    assert '<script src="/map-fallback.js"></script>' in page_response.text
    assert "cdn.jsdelivr.net" not in page_response.text

    fallback_response = client.get("/map-fallback.js")
    assert fallback_response.status_code == 200
    assert "window.maplibregl" in fallback_response.text
    assert "Fallback route view" in fallback_response.text
