from __future__ import annotations

from .feature_api import router as feature_router
from .garage_v2 import router as garage_router
from .map_assets import MapAssetProxyMiddleware
from .map_assets import router as map_assets_router
from .pwa import router as pwa_router
from .resilience import DashboardMapFallbackMiddleware
from .resilience import router as resilience_router
from .web import app

app.include_router(garage_router)
app.include_router(feature_router)
app.include_router(pwa_router)
app.include_router(resilience_router)
app.include_router(map_assets_router)
app.add_middleware(DashboardMapFallbackMiddleware)
app.add_middleware(MapAssetProxyMiddleware)
