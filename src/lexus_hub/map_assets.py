"""Same-origin MapLibre assets for private dashboard map reliability."""

from __future__ import annotations

from functools import lru_cache

import httpx
from fastapi import APIRouter
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

router = APIRouter(tags=["map assets"])

_MAPLIBRE_VERSION = "6.3.0"
_MAPLIBRE_BASE = (
    "https://cdn.jsdelivr.net/npm/"
    f"maplibre-gl@{_MAPLIBRE_VERSION}/dist"
)
_CDN_CSS = (
    f"https://cdn.jsdelivr.net/npm/maplibre-gl@{_MAPLIBRE_VERSION}/dist/"
    "maplibre-gl.css"
)
_CDN_JS = (
    f"https://cdn.jsdelivr.net/npm/maplibre-gl@{_MAPLIBRE_VERSION}/dist/"
    "maplibre-gl.js"
)
_LOCAL_CSS = "/vendor/maplibre-gl.css"
_LOCAL_JS = "/vendor/maplibre-gl.js"
_FALLBACK_JS = "/map-fallback.js"


@lru_cache(maxsize=4)
def _download_asset(name: str) -> bytes:
    url = f"{_MAPLIBRE_BASE}/{name}"
    response = httpx.get(
        url,
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "Lexus-Personal-Hub/0.3"},
    )
    response.raise_for_status()
    return response.content


def _asset_response(name: str, media_type: str) -> Response:
    try:
        content = _download_asset(name)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except httpx.HTTPError as exc:
        return Response(
            content=f"/* MapLibre asset unavailable: {type(exc).__name__} */\n",
            status_code=502,
            media_type=media_type,
            headers={"Cache-Control": "no-store"},
        )


@router.get(_LOCAL_JS, include_in_schema=False)
def maplibre_js() -> Response:
    return _asset_response("maplibre-gl.js", "application/javascript")


@router.get(_LOCAL_CSS, include_in_schema=False)
def maplibre_css() -> Response:
    return _asset_response("maplibre-gl.css", "text/css")


class MapAssetProxyMiddleware(BaseHTTPMiddleware):
    """Rewrite dashboard CDN MapLibre assets to same-origin proxy endpoints."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path not in {"/", "/garage"}:
            return response
        if "text/html" not in response.headers.get("content-type", ""):
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode("utf-8", errors="replace")
        text = text.replace(_CDN_CSS, _LOCAL_CSS)

        local_script = f'<script src="{_LOCAL_JS}"></script>'
        fallback_script = f'<script src="{_FALLBACK_JS}"></script>'
        cdn_script = f'<script src="{_CDN_JS}"></script>'
        if cdn_script in text:
            replacement = local_script
            if fallback_script not in text:
                replacement += "\n" + fallback_script
            text = text.replace(cdn_script, replacement, 1)

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=text,
            status_code=response.status_code,
            headers=headers,
            media_type="text/html",
        )
