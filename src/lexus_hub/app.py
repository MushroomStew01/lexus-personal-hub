from __future__ import annotations

from .feature_api import router as feature_router
from .web import app

app.include_router(feature_router)
