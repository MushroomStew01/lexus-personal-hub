from __future__ import annotations

from .feature_api import router as feature_router
from .garage_v2 import router as garage_router
from .map_assets import MapAssetProxyMiddleware
from .map_assets import router as map_assets_router
from .mobile_app_v2 import GarageReturnLinkMiddleware
from .mobile_app_v3 import router as mobile_app_v3_router
from .mobile_enhancements import router as mobile_enhancements_router
from .mobile_resilience import MobileResilienceMiddleware
from .mobile_resilience import router as mobile_resilience_router
from .pwa import router as pwa_router
from .resilience import DashboardMapFallbackMiddleware
from .resilience import router as resilience_router
from .stability import StabilityMiddleware
from .web import app

app.include_router(garage_router)
app.include_router(feature_router)
# Polished mobile shell owns /app. The PWA router still provides manifest/icons/service worker.
app.include_router(mobile_app_v3_router)
app.include_router(pwa_router)
app.include_router(resilience_router)
app.include_router(map_assets_router)
# Trip details, reverse-geocoding, connection routing, and refresh APIs used by the mobile shell.
app.include_router(mobile_enhancements_router)
app.include_router(mobile_resilience_router)
app.add_middleware(DashboardMapFallbackMiddleware)
app.add_middleware(MapAssetProxyMiddleware)
# Keep cached connection targets available when the installed PWA opens before APIs respond.
app.add_middleware(MobileResilienceMiddleware)
# Garage remains the full driving-intelligence page but returns to /app.
app.add_middleware(GarageReturnLinkMiddleware)
# Presentation-only hardening for iOS, timestamps, icons, and fixed-navigation overlap.
app.add_middleware(StabilityMiddleware)
