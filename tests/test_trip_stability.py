from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lexus_hub.config import Settings
from lexus_hub.mobile_enhancements import _trip_metrics
from lexus_hub.models import Snapshot, Trip
from lexus_hub.trip_experience import TripExperienceMiddleware


def test_top_speed_does_not_invent_peak_from_coarse_odometer_segments():
    start = datetime(2026, 8, 15, 17, 0, 0)
    trip = Trip(
        vehicle_id=1,
        started_at=start,
        ended_at=start + timedelta(minutes=15),
        last_movement_at=start + timedelta(minutes=15),
        start_odometer_km=100.0,
        end_odometer_km=105.0,
        distance_km=5.0,
        is_open=False,
    )
    snapshots = [
        Snapshot(
            vehicle_id=1,
            observed_at=start,
            source_updated_at=start,
            odometer_km=100.0,
            speed_kph=0.0,
            latitude=43.40,
            longitude=-80.30,
        ),
        Snapshot(
            vehicle_id=1,
            observed_at=start + timedelta(minutes=10),
            source_updated_at=start + timedelta(minutes=10),
            odometer_km=104.0,
            speed_kph=5.8,
            latitude=43.43,
            longitude=-80.31,
        ),
        Snapshot(
            vehicle_id=1,
            observed_at=start + timedelta(minutes=15),
            source_updated_at=start + timedelta(minutes=15),
            odometer_km=105.0,
            speed_kph=0.0,
            latitude=43.44,
            longitude=-80.32,
        ),
    ]

    metrics = _trip_metrics(snapshots, trip, Settings(_env_file=None))

    assert metrics["average_speed_kph"] == 20.0
    assert metrics["top_speed_kph"] == 5.8
    assert metrics["sampled_top_speed_kph"] == 5.8
    assert metrics["speed_samples"] == 3


def test_duplicate_toyota_revision_is_only_one_speed_sample():
    start = datetime(2026, 8, 15, 17, 0, 0)
    trip = Trip(
        vehicle_id=1,
        started_at=start,
        ended_at=start + timedelta(minutes=15),
        last_movement_at=start + timedelta(minutes=15),
        start_odometer_km=100.0,
        end_odometer_km=105.0,
        distance_km=5.0,
        is_open=False,
    )
    revision = start + timedelta(minutes=5)
    snapshots = [
        Snapshot(
            vehicle_id=1,
            observed_at=start + timedelta(minutes=5),
            source_updated_at=revision,
            odometer_km=101.0,
            speed_kph=55.0,
        ),
        Snapshot(
            vehicle_id=1,
            observed_at=start + timedelta(minutes=10),
            source_updated_at=revision,
            odometer_km=104.0,
            speed_kph=55.0,
        ),
    ]
    metrics = _trip_metrics(snapshots, trip, Settings(_env_file=None))
    assert metrics["top_speed_kph"] == 55.0
    assert metrics["speed_samples"] == 1


def test_garage_redirects_back_to_inline_trips():
    app = FastAPI()

    @app.get("/garage")
    def garage():
        return {"legacy": True}

    app.add_middleware(TripExperienceMiddleware)
    response = TestClient(app).get("/garage", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/app#trips"
