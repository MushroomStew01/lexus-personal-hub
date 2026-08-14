from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from lexus_hub.config import Settings
from lexus_hub.db import Base
from lexus_hub.insights import (
    add_maintenance_record,
    add_named_location_from_current,
    current_vehicle_location,
    fuel_analytics,
    maintenance_history,
    trip_replay,
)
from lexus_hub.models import Trip
from lexus_hub.providers.base import VehicleReading
from lexus_hub.storage import add_fuel_fill, save_snapshot
from lexus_hub.timeutil import utcnow


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        provider="mock",
        store_location=True,
        show_exact_location=True,
        min_trip_delta_km=0.2,
    )


def test_named_private_location_hides_name_in_status():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = _settings()
    now = utcnow()

    with Session(engine) as session:
        vehicle, _snapshot = save_snapshot(
            session,
            VehicleReading(
                provider_vehicle_id="mock:primary",
                display_name="Test Lexus",
                observed_at=now,
                odometer_km=1000,
                latitude=43.45,
                longitude=-80.49,
            ),
            "mock",
            settings,
        )
        location = add_named_location_from_current(
            session,
            settings,
            name="Home",
            radius_m=250,
            is_private=True,
        )
        assert location.vehicle_id == vehicle.id
        status = current_vehicle_location(session, settings)
        assert status["label"] == "Private location"
        assert status["latitude"] == 43.45


def test_trip_replay_includes_saved_telemetry():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = _settings()
    now = utcnow()

    with Session(engine) as session:
        save_snapshot(
            session,
            VehicleReading(
                provider_vehicle_id="mock:primary",
                display_name="Test Lexus",
                observed_at=now,
                odometer_km=1000,
                fuel_percent=80,
                speed_kph=0,
                latitude=43.45,
                longitude=-80.49,
            ),
            "mock",
            settings,
        )
        save_snapshot(
            session,
            VehicleReading(
                provider_vehicle_id="mock:primary",
                display_name="Test Lexus",
                observed_at=now + timedelta(minutes=5),
                odometer_km=1004,
                fuel_percent=79,
                speed_kph=55,
                latitude=43.47,
                longitude=-80.51,
            ),
            "mock",
            settings,
        )
        trip = session.scalar(select(Trip))
        assert trip is not None
        replay = trip_replay(session, settings, trip.id)
        assert replay is not None
        assert len(replay["points"]) == 2
        assert replay["points"][1]["speed_kph"] == 55
        assert replay["points"][1]["fuel_percent"] == 79


def test_fuel_analytics_and_maintenance_use_odometer():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = _settings()
    now = utcnow()

    with Session(engine) as session:
        vehicle, _snapshot = save_snapshot(
            session,
            VehicleReading(
                provider_vehicle_id="mock:primary",
                display_name="Test Lexus",
                observed_at=now,
                odometer_km=1100,
            ),
            "mock",
            settings,
        )
        add_fuel_fill(session, vehicle, liters=9, total_cost=18, odometer_km=1000)
        add_fuel_fill(session, vehicle, liters=10, total_cost=20, odometer_km=1100)

        stats = fuel_analytics(session, settings)
        assert stats["average_l_per_100km"] == 10.0
        assert stats["average_cost_per_km"] == 0.2

        record = add_maintenance_record(session, settings, kind="Oil change", cost=120)
        assert record.odometer_km == 1100
        history = maintenance_history(session, settings)
        assert history[0]["kind"] == "Oil change"
        assert history[0]["cost"] == 120
