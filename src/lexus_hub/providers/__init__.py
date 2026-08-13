from __future__ import annotations

from ..config import Settings
from .base import VehicleProvider
from .mock import MockProvider


def get_provider(settings: Settings) -> VehicleProvider:
    return MockProvider(settings)
