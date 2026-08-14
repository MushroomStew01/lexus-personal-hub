from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from ..config import Settings
from ..timeutil import utcnow
from .base import VehicleReading

_STATUS_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("front_driver_door_lock", ("front driver door lock",), "lock"),
    ("front_passenger_door_lock", ("front passenger door lock",), "lock"),
    ("rear_driver_door_lock", ("rear driver door lock",), "lock"),
    ("rear_passenger_door_lock", ("rear passenger door lock",), "lock"),
    ("trunk_door_lock", ("trunk door lock",), "lock"),
    ("front_driver_window", ("front driver window",), "opening"),
    ("front_passenger_window", ("front passenger window",), "opening"),
    ("rear_driver_window", ("rear driver window",), "opening"),
    ("rear_passenger_window", ("rear passenger window",), "opening"),
    ("front_driver_door", ("front driver door",), "opening"),
    ("front_passenger_door", ("front passenger door",), "opening"),
    ("rear_driver_door", ("rear driver door",), "opening"),
    ("rear_passenger_door", ("rear passenger door",), "opening"),
    ("moonroof", ("moonroof",), "opening"),
    ("hood", (" hood ", "_hood_", " hood"), "opening"),
    ("trunk", (" trunk ", "_trunk_", " trunk"), "opening"),
    ("front_driver_tire", ("front driver tire",), "number"),
    ("front_passenger_tire", ("front passenger tire",), "number"),
    ("rear_driver_tire", ("rear driver tire",), "number"),
    ("rear_passenger_tire", ("rear passenger tire",), "number"),
    ("spare_tire", ("spare tire pressure",), "number"),
    ("next_service", ("next service",), "distance"),
    ("last_tire_pressure_update", ("last tire pressure update",), "text"),
    ("last_update", ("last update timestamp", "last update"), "text"),
    ("remote_start", ("remote start",), "running"),
)


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
        return f" {state.get('entity_id', '')} {attrs.get('friendly_name', '')} ".lower()

    @staticmethod
    def _parse_ha_timestamp(value: object) -> datetime | None:
        if not value:
            return None
        text = str(value).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    @staticmethod
    def _coordinates(state: dict[str, Any] | None) -> tuple[float | None, float | None]:
        if not state:
            return None, None
        attrs = state.get("attributes") or {}
        latitude = attrs.get("latitude")
        longitude = attrs.get("longitude")
        try:
            lat = float(latitude) if latitude is not None else None
            lon = float(longitude) if longitude is not None else None
        except (TypeError, ValueError):
            return None, None
        if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None, None
        return lat, lon

    def _vehicle_states(self, states: list[dict[str, Any]]) -> list[dict[str, Any]]:
        match = self.settings.vehicle_display_name.strip().lower()
        if not match or match == "my lexus":
            return states
        matched = [item for item in states if match in self._text(item)]
        return matched or states

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

        candidates = [
            item
            for item in self._vehicle_states(states)
            if any(term in self._text(item) for term in terms)
        ]
        return candidates[0] if candidates else None

    def _location_state(self, states: list[dict[str, Any]]) -> dict[str, Any] | None:
        if self.settings.ha_location_entity:
            return self._find(states, self.settings.ha_location_entity, ())
        vehicle_states = self._vehicle_states(states)
        for terms in (
            ("current location", "current_location"),
            ("last parked location", "last_parked_location"),
            ("parking location", "parking_location"),
        ):
            found = self._find(vehicle_states, None, terms)
            if found is not None and self._coordinates(found) != (None, None):
                return found
        return None

    @staticmethod
    def _friendly_name(state: dict[str, Any]) -> str:
        attrs = state.get("attributes") or {}
        return str(attrs.get("friendly_name") or state.get("entity_id") or "")

    @staticmethod
    def _binary_label(raw: str, kind: str) -> str:
        value = raw.strip().lower()
        if kind == "lock":
            if value in {"off", "locked", "closed", "false", "0"}:
                return "Locked"
            if value in {"on", "unlocked", "open", "true", "1"}:
                return "Unlocked"
        if kind == "opening":
            if value in {"off", "closed", "locked", "false", "0"}:
                return "Closed"
            if value in {"on", "open", "unlocked", "true", "1"}:
                return "Open"
        if kind == "running":
            if value in {"on", "running", "true", "1"}:
                return "Running"
            if value in {"off", "stopped", "false", "0"}:
                return "Off"
        return raw

    def _status_record(
        self,
        state: dict[str, Any],
        kind: str,
    ) -> dict[str, Any]:
        raw = str(state.get("state") or "")
        unit = self._unit(state)
        value: object = raw
        display = raw

        if kind == "number":
            number = self._number(state)
            value = number
            display = "—" if number is None else f"{number:g} {unit}".strip()
        elif kind == "distance":
            distance = self._distance_km(state)
            value = distance
            unit = "km"
            display = "—" if distance is None else f"{distance:.0f} km"
        elif kind in {"opening", "lock", "running"}:
            value = self._binary_label(raw, kind)
            display = str(value)

        return {
            "value": value,
            "display": display,
            "unit": unit,
            "entity_id": state.get("entity_id"),
            "friendly_name": self._friendly_name(state),
            "updated_at": state.get("last_updated"),
        }

    def _status_map(self, states: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        vehicle_states = self._vehicle_states(states)
        status: dict[str, dict[str, Any]] = {}
        used_entities: set[str] = set()
        for key, terms, kind in _STATUS_RULES:
            for item in vehicle_states:
                entity_id = str(item.get("entity_id") or "")
                if entity_id in used_entities:
                    continue
                text = self._text(item)
                if any(term in text for term in terms):
                    status[key] = self._status_record(item, kind)
                    used_entities.add(entity_id)
                    break
        return status

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
        location = self._location_state(states)
        latitude, longitude = self._coordinates(location)
        status = self._status_map(states)
        source_updated_at = self._parse_ha_timestamp(odometer.get("last_updated"))
        return VehicleReading(
            provider_vehicle_id="ha:primary",
            display_name=self.settings.vehicle_display_name,
            observed_at=utcnow(),
            source_updated_at=source_updated_at,
            make="Lexus",
            odometer_km=self._distance_km(odometer),
            fuel_percent=self._number(fuel),
            range_km=self._distance_km(range_state),
            speed_kph=self._speed_kph(speed),
            latitude=latitude,
            longitude=longitude,
            raw={"status": status},
        )

    async def discover(self) -> dict[str, Any]:
        states = await self._states()
        vehicle_states = self._vehicle_states(states)
        candidates: list[dict[str, Any]] = []
        for item in vehicle_states:
            text = self._text(item)
            if any(
                term in text
                for term in (
                    "odometer",
                    "fuel",
                    "distance to empty",
                    "speed",
                    "tire",
                    "door",
                    "window",
                    "moonroof",
                    "hood",
                    "trunk",
                    "next service",
                    "last update",
                    "current location",
                    "last parked location",
                )
            ):
                attrs = item.get("attributes") or {}
                candidates.append(
                    {
                        "entity_id": item.get("entity_id"),
                        "friendly_name": attrs.get("friendly_name"),
                        "state": item.get("state"),
                        "unit": attrs.get("unit_of_measurement"),
                    }
                )
        location = self._location_state(states)
        return {
            "provider": self.name,
            "vehicle": self.settings.vehicle_display_name,
            "location_entity": location.get("entity_id") if location else None,
            "candidates": candidates,
            "status": self._status_map(states),
        }
