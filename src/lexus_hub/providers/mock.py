from __future__ import annotations

from datetime import timedelta

from ..config import Settings
from ..timeutil import utcnow
from .base import VehicleReading


class MockProvider:
    name = "mock"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def fetch(self) -> VehicleReading:
        now = utcnow()
        day_fraction = (now.hour * 60 + now.minute) / 1440
        return VehicleReading(
            provider_vehicle_id="mock:primary",
            display_name=self.settings.vehicle_display_name,
            observed_at=now,
            source_updated_at=now - timedelta(seconds=15),
            make="Lexus",
            model="IS 300 F Sport",
            year=2023,
            odometer_km=round(54631 + day_fraction * 25, 1),
            fuel_percent=round(max(10.0, 100.0 - day_fraction * 25), 1),
            range_km=round(max(50.0, 431.0 - day_fraction * 180), 1),
            speed_kph=0,
            raw={
                "status": {
                    "front_driver_tire": {"value": 40, "display": "40 psi", "unit": "psi"},
                    "front_passenger_tire": {"value": 39, "display": "39 psi", "unit": "psi"},
                    "rear_driver_tire": {"value": 40, "display": "40 psi", "unit": "psi"},
                    "rear_passenger_tire": {"value": 39, "display": "39 psi", "unit": "psi"},
                    "front_driver_door": {"value": "Closed", "display": "Closed"},
                    "front_passenger_door": {"value": "Closed", "display": "Closed"},
                    "rear_driver_door": {"value": "Closed", "display": "Closed"},
                    "rear_passenger_door": {"value": "Closed", "display": "Closed"},
                    "front_driver_window": {"value": "Closed", "display": "Closed"},
                    "front_passenger_window": {"value": "Closed", "display": "Closed"},
                    "rear_driver_window": {"value": "Closed", "display": "Closed"},
                    "rear_passenger_window": {"value": "Closed", "display": "Closed"},
                    "front_driver_door_lock": {"value": "Locked", "display": "Locked"},
                    "front_passenger_door_lock": {"value": "Locked", "display": "Locked"},
                    "rear_driver_door_lock": {"value": "Locked", "display": "Locked"},
                    "rear_passenger_door_lock": {"value": "Locked", "display": "Locked"},
                    "trunk": {"value": "Closed", "display": "Closed"},
                    "hood": {"value": "Closed", "display": "Closed"},
                    "moonroof": {"value": "Closed", "display": "Closed"},
                    "last_update": {"value": now.isoformat(), "display": now.isoformat()},
                }
            },
        )

    async def discover(self) -> dict[str, object]:
        return {"provider": self.name, "ready": True}
