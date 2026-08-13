from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(slots=True)
class VehicleReading:
    provider_vehicle_id: str
    display_name: str
    observed_at: datetime
    source_updated_at: datetime | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    odometer_km: float | None = None
    fuel_percent: float | None = None
    range_km: float | None = None
    speed_kph: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class VehicleProvider(Protocol):
    name: str

    async def fetch(self) -> VehicleReading:
        """Fetch one current vehicle reading."""

    async def discover(self) -> dict[str, Any]:
        """Return provider-specific setup diagnostics."""
