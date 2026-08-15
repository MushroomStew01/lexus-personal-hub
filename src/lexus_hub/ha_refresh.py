from __future__ import annotations

from typing import Any

import httpx

from .config import Settings


def _headers(settings: Settings) -> dict[str, str]:
    if not settings.ha_token:
        raise RuntimeError("HA_TOKEN is required for Home Assistant refresh support.")
    return {
        "Authorization": f"Bearer {settings.ha_token}",
        "Content-Type": "application/json",
    }


def _state_text(state: dict[str, Any]) -> str:
    attrs = state.get("attributes") or {}
    return (
        f"{state.get('entity_id', '')} {attrs.get('friendly_name', '')}"
    ).strip().lower()


def _is_safe_refresh_button(state: dict[str, Any], settings: Settings) -> bool:
    entity_id = str(state.get("entity_id") or "")
    if not entity_id.startswith("button."):
        return False
    text = _state_text(state)
    if "refresh" not in text:
        return False
    vehicle_hint = settings.vehicle_display_name.strip().lower()
    vehicle_match = bool(vehicle_hint and vehicle_hint != "my lexus" and vehicle_hint in text)
    provider_match = any(term in text for term in ("toyota", "lexus", "vehicle status", "car status"))
    return vehicle_match or provider_match


async def discover_refresh_options(settings: Settings) -> dict[str, object]:
    if settings.provider != "home_assistant":
        return {"supported": False, "reason": "Provider is not Home Assistant."}
    if not settings.ha_token:
        return {"supported": False, "reason": "HA_TOKEN is not configured."}

    base = settings.ha_base_url.rstrip("/")
    async with httpx.AsyncClient(
        headers=_headers(settings),
        verify=settings.ha_verify_ssl,
        timeout=15,
    ) as client:
        states_response = await client.get(f"{base}/api/states")
        states_response.raise_for_status()
        states = states_response.json()

        services_response = await client.get(f"{base}/api/services")
        services_response.raise_for_status()
        services = services_response.json()

    buttons: list[dict[str, str]] = []
    if isinstance(states, list):
        for state in states:
            if not isinstance(state, dict) or not _is_safe_refresh_button(state, settings):
                continue
            attrs = state.get("attributes") or {}
            buttons.append(
                {
                    "entity_id": str(state.get("entity_id") or ""),
                    "friendly_name": str(attrs.get("friendly_name") or ""),
                }
            )

    refresh_services: list[str] = []
    if isinstance(services, list):
        for item in services:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or "")
            domain_l = domain.lower()
            if "toyota" not in domain_l and "lexus" not in domain_l:
                continue
            service_block = item.get("services")
            if isinstance(service_block, dict):
                names = service_block.keys()
            elif isinstance(service_block, list):
                names = service_block
            else:
                names = []
            for name in names:
                service_name = str(name)
                if "refresh" in service_name.lower():
                    refresh_services.append(f"{domain}.{service_name}")

    configured = settings.ha_refresh_button_entity
    selected = configured or (buttons[0]["entity_id"] if buttons else None)
    return {
        "supported": bool(selected),
        "selected_button": selected,
        "configured_button": configured,
        "buttons": buttons,
        "refresh_services": sorted(set(refresh_services)),
        "note": (
            "Only a Home Assistant button whose name clearly indicates vehicle-status refresh "
            "is eligible for automatic pressing. Other Toyota/Lexus services are listed only "
            "for diagnostics and are never called automatically."
        ),
    }


async def request_vehicle_refresh(settings: Settings) -> dict[str, object]:
    options = await discover_refresh_options(settings)
    selected = options.get("selected_button")
    if not selected:
        return {
            "requested": False,
            "reason": "No safe Home Assistant vehicle-status refresh button was found.",
            "options": options,
        }

    entity_id = str(selected)
    base = settings.ha_base_url.rstrip("/")
    async with httpx.AsyncClient(
        headers=_headers(settings),
        verify=settings.ha_verify_ssl,
        timeout=20,
    ) as client:
        response = await client.post(
            f"{base}/api/services/button/press",
            json={"entity_id": entity_id},
        )
        response.raise_for_status()

    return {
        "requested": True,
        "source": "home_assistant_button",
        "entity_id": entity_id,
    }
