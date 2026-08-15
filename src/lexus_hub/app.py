from __future__ import annotations

from .feature_api import router as feature_router
from .garage_v2 import router as garage_router
from .map_assets import MapAssetProxyMiddleware
from .map_assets import router as map_assets_router
from .mobile_app_v2 import GarageReturnLinkMiddleware
from .mobile_app_v2 import router as mobile_app_v2_router
from .mobile_enhancements import router as mobile_enhancements_router
from .mobile_resilience import MobileResilienceMiddleware
from .mobile_resilience import router as mobile_resilience_router
from .pwa import router as pwa_router
from .resilience import DashboardMapFallbackMiddleware
from .resilience import router as resilience_router
from .web import app

app.include_router(garage_router)
app.include_router(feature_router)
# Register the redesigned /app before the legacy PWA shell so it wins route matching.
app.include_router(mobile_app_v2_router)
# Keep manifest, icons, service worker, and health-score resources from the PWA module.
app.include_router(pwa_router)
app.include_router(resilience_router)
app.include_router(map_assets_router)
# These routers still provide trip-details, address, access, and refresh APIs used by mobile v2.
app.include_router(mobile_enhancements_router)
app.include_router(mobile_resilience_router)
app.add_middleware(DashboardMapFallbackMiddleware)
app.add_middleware(MapAssetProxyMiddleware)
# This injects cached connection targets for the offline PWA shell without changing the v2 layout.
app.add_middleware(MobileResilienceMiddleware)
app.add_middleware(GarageReturnLinkMiddleware)
