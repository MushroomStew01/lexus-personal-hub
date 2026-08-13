from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from lexus_hub.config import Settings
from lexus_hub.db import Base
from lexus_hub.models import Trip
from lexus_hub.providers.base import VehicleReading
from lexus_hub.storage import save_snapshot
from lexus_hub.timeutil import utcnow


def test_odometer_history_creates_and_closes_trip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        min_trip_delta_km=0.2,
        trip_idle_close_minutes=30,
    )
    start = utcnow()

    with Session(engine) as session:
        first = VehicleReading(
            provider_vehicle_id="mock:primary",
            display_name="Test Lexus",
            observed_at=start,
            odometer_km=1000.0,
        )
        second = VehicleReading(
            provider_vehicle_id="mock:primary",
            display_name="Test Lexus",
            observed_at=start + timedelta(minutes=15),
            odometer_km=1004.0,
        )
        third = VehicleReading(
            provider_vehicle_id="mock:primary",
            display_name="Test Lexus",
            observed_at=start + timedelta(minutes=50),
            odometer_km=1004.0,
        )

        save_snapshot(session, first, "mock", settings)
        save_snapshot(session, second, "mock", settings)
        trip = session.scalar(select(Trip))
        assert trip is not None
        assert trip.is_open is True
        assert trip.distance_km == 4.0

        save_snapshot(session, third, "mock", settings)
        assert trip.is_open is False
        assert trip.ended_at == second.observed_at
