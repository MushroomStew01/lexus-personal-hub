from __future__ import annotations

from typing import Any

import httpx

from .config import Settings

_SAFE_REFRESH_SERVICES = {"toyota_na.refresh"}


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
    vehicle_match = bool(
        vehicle_hint
        and vehicle_hint != "my lexus"
        and vehicle_hint in text
    )
    provider_match = any(
        term in text
        for term in ("toyota", "lexus", "vehicle status", "car status")
    )
    return vehicle_match or provider_match


def _refresh_services(services: object) -> list[str]:
    found: list[str] = []
    if not isinstance(services, list):
        return found
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
                found.append(f"{domain}.{service_name}")
    return sorted(set(found))


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

    refresh_services = _refresh_services(services)
    safe_services = [
        service_name
        for service_name in refresh_services
        if service_name in _SAFE_REFRESH_SERVICES
    ]

    configured_button = settings.ha_refresh_button_entity
    selected_button = configured_button or (
        buttons[0]["entity_id"] if buttons else None
    )
    selected_service = safe_services[0] if safe_services else None
    service_ready = bool(selected_service and settings.ha_refresh_device_id)

    reason = None
    if not selected_button and selected_service and not settings.ha_refresh_device_id:
        reason = (
            f"{selected_service} is available, but HA_REFRESH_DEVICE_ID is not configured."
        )
    elif not selected_button and not selected_service:
        reason = "No supported Toyota/Lexus vehicle-status refresh action was found."

    return {
        "supported": bool(selected_button or service_ready),
        "reason": reason,
        "selected_button": selected_button,
        "configured_button": configured_button,
        "buttons": buttons,
        "selected_service": selected_service,
        "configured_device_id": bool(settings.ha_refresh_device_id),
        "refresh_services": refresh_services,
        "note": (
            "Lexus Hub can use either a clearly named refresh button or the exact "
            "toyota_na.refresh service. The Toyota NA service requires the Home Assistant "
            "vehicle device ID and only refreshes telemetry; it does not issue lock, start, "
            "unlock, hazard, or climate commands."
        ),
    }


async def request_vehicle_refresh(settings: Settings) -> dict[str, object]:
    options = await discover_refresh_options(settings)
    selected_button = options.get("selected_button")
    selected_service = options.get("selected_service")
    base = settings.ha_base_url.rstrip("/")

    if selected_button:
        entity_id = str(selected_button)
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

    if selected_service in _SAFE_REFRESH_SERVICES and settings.ha_refresh_device_id:
        domain, service_name = str(selected_service).split(".", 1)
        async with httpx.AsyncClient(
            headers=_headers(settings),
            verify=settings.ha_verify_ssl,
            timeout=30,
        ) as client:
            response = await client.post(
                f"{base}/api/services/{domain}/{service_name}",
                json={"vehicle": settings.ha_refresh_device_id},
            )
            response.raise_for_status()
        return {
            "requested": True,
            "source": "home_assistant_service",
            "service": selected_service,
        }

    return {
        "requested": False,
        "reason": options.get("reason") or "No safe vehicle-status refresh action is configured.",
        "options": options,
    }
