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
            model="Demo",
            year=2026,
            odometer_km=round(42000 + day_fraction * 25, 1),
            fuel_percent=round(max(10.0, 72.0 - day_fraction * 25), 1),
            range_km=round(max(50.0, 510.0 - day_fraction * 180), 1),
            speed_kph=0,
            raw={"mode": "mock"},
        )

    async def discover(self) -> dict[str, object]:
        return {"provider": self.name, "ready": True}
