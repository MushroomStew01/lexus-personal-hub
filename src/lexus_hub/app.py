from __future__ import annotations

from .feature_api import router as feature_router
from .pwa import router as pwa_router
from .resilience import DashboardMapFallbackMiddleware
from .resilience import router as resilience_router
from .web import app

app.include_router(feature_router)
app.include_router(pwa_router)
app.include_router(resilience_router)
app.add_middleware(DashboardMapFallbackMiddleware)
