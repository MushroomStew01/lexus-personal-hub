from __future__ import annotations

from ..config import Settings
from .base import VehicleProvider
from .ha import HAProvider
from .mock import MockProvider

_PROVIDER_TYPES = {
    "mock": MockProvider,
    "home_assistant": HAProvider,
}


def get_provider(settings: Settings) -> VehicleProvider:
    provider_type = _PROVIDER_TYPES[settings.provider]
    return provider_type(settings)
