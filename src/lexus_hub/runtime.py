from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from .providers.base import VehicleReading


@dataclass
class RuntimeState:
    reading: VehicleReading | None = None
    last_error: str | None = None
    last_poll: datetime | None = None


state = RuntimeState()
lock = asyncio.Lock()
