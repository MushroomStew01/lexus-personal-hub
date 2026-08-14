from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from lexus_hub.config import Settings
from lexus_hub.db import Base
from lexus_hub.models import Trip, TripPoint
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


def test_location_history_creates_trip_points():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        min_trip_delta_km=0.2,
        trip_idle_close_minutes=30,
        store_location=True,
        show_exact_location=True,
    )
    start = utcnow()

    with Session(engine) as session:
        readings = [
            VehicleReading(
                provider_vehicle_id="mock:primary",
                display_name="Test Lexus",
                observed_at=start,
                odometer_km=1000.0,
                latitude=43.4516,
                longitude=-80.4925,
            ),
            VehicleReading(
                provider_vehicle_id="mock:primary",
                display_name="Test Lexus",
                observed_at=start + timedelta(minutes=10),
                odometer_km=1002.0,
                latitude=43.4550,
                longitude=-80.5000,
            ),
            VehicleReading(
                provider_vehicle_id="mock:primary",
                display_name="Test Lexus",
                observed_at=start + timedelta(minutes=20),
                odometer_km=1004.0,
                latitude=43.4600,
                longitude=-80.5100,
            ),
        ]
        for reading in readings:
            save_snapshot(session, reading, "mock", settings)

        trip = session.scalar(select(Trip))
        assert trip is not None
        assert trip.start_latitude == 43.4516
        assert trip.start_longitude == -80.4925
        assert trip.end_latitude == 43.4600
        assert trip.end_longitude == -80.5100

        points = session.scalars(
            select(TripPoint).where(TripPoint.trip_id == trip.id).order_by(TripPoint.observed_at)
        ).all()
        assert len(points) == 3
        assert points[0].latitude == 43.4516
        assert points[-1].longitude == -80.5100
