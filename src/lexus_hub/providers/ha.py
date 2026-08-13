from __future__ import annotations

from typing import Any

import httpx

from ..config import Settings
from ..timeutil import utcnow
from .base import VehicleReading


class HAProvider:
    name = "home_assistant"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def _states(self) -> list[dict[str, Any]]:
        if not self.settings.ha_token:
            raise RuntimeError("HA_TOKEN is required when PROVIDER=home_assistant.")
        url = self.settings.ha_base_url.rstrip("/") + "/api/states"
        headers = {"Authorization": f"Bearer {self.settings.ha_token}"}
        async with httpx.AsyncClient(
            headers=headers,
            verify=self.settings.ha_verify_ssl,
            timeout=15,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected Home Assistant response.")
        return payload

    @staticmethod
    def _number(state: dict[str, Any] | None) -> float | None:
        if not state:
            return None
        raw = state.get("state")
        if raw in {None, "", "unknown", "unavailable"}:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _unit(state: dict[str, Any] | None) -> str:
        if not state:
            return ""
        attrs = state.get("attributes") or {}
        return str(attrs.get("unit_of_measurement") or "").strip().lower()

    @classmethod
    def _distance_km(cls, state: dict[str, Any] | None) -> float | None:
        value = cls._number(state)
        if value is None:
            return None
        unit = cls._unit(state)
        if unit in {"mi", "mile", "miles"}:
            return value * 1.609344
        if unit in {"m", "meter", "meters"}:
            return value / 1000
        return value

    @classmethod
    def _speed_kph(cls, state: dict[str, Any] | None) -> float | None:
        value = cls._number(state)
        if value is None:
            return None
        unit = cls._unit(state)
        if unit in {"mph", "mi/h"}:
            return value * 1.609344
        if unit in {"m/s", "mps"}:
            return value * 3.6
        return value

    @staticmethod
    def _text(state: dict[str, Any]) -> str:
        attrs = state.get("attributes") or {}
        return f"{state.get('entity_id', '')} {attrs.get('friendly_name', '')}".lower()

    def _find(
        self,
        states: list[dict[str, Any]],
        explicit: str | None,
        terms: tuple[str, ...],
    ) -> dict[str, Any] | None:
        if explicit:
            found = next((item for item in states if item.get("entity_id") == explicit), None)
            if found is None:
                raise RuntimeError(f"Configured Home Assistant entity was not found: {explicit}")
            return found

        match = self.settings.vehicle_display_name.strip().lower()
        if match == "my lexus":
            match = ""
        candidates = [item for item in states if any(term in self._text(item) for term in terms)]
        if match:
            matched = [item for item in candidates if match in self._text(item)]
            if matched:
                candidates = matched
        return candidates[0] if candidates else None

    async def fetch(self) -> VehicleReading:
        states = await self._states()
        odometer = self._find(states, self.settings.ha_odometer_entity, ("odometer",))
        if odometer is None:
            raise RuntimeError(
                "Could not find an odometer entity. Run `lexus-hub provider-discover` "
                "and set HA_ODOMETER_ENTITY."
            )
        fuel = self._find(states, self.settings.ha_fuel_entity, ("fuel level", "fuel_level"))
        range_state = self._find(
            states,
            self.settings.ha_range_entity,
            ("distance to empty", "distance_to_empty", "fuel range"),
        )
        speed = self._find(states, self.settings.ha_speed_entity, ("speed",))
        return VehicleReading(
            provider_vehicle_id="ha:primary",
            display_name=self.settings.vehicle_display_name,
            observed_at=utcnow(),
            make="Lexus",
            odometer_km=self._distance_km(odometer),
            fuel_percent=self._number(fuel),
            range_km=self._distance_km(range_state),
            speed_kph=self._speed_kph(speed),
        )

    async def discover(self) -> dict[str, Any]:
        states = await self._states()
        candidates: list[dict[str, Any]] = []
        for item in states:
            text = self._text(item)
            if any(term in text for term in ("odometer", "fuel", "distance to empty", "speed")):
                attrs = item.get("attributes") or {}
                candidates.append(
                    {
                        "entity_id": item.get("entity_id"),
                        "friendly_name": attrs.get("friendly_name"),
                        "state": item.get("state"),
                        "unit": attrs.get("unit_of_measurement"),
                    }
                )
        return {"provider": self.name, "candidates": candidates}
