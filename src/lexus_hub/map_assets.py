"""Same-origin MapLibre assets for private dashboard map reliability."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
_VENDOR_DIR = Path("/app/vendor")


@lru_cache(maxsize=4)
def _download_asset(name: str) -> bytes:
    url = f"{_MAPLIBRE_BASE}/{name}"
    response = httpx.get(
        url,
        timeout=120.0,
        follow_redirects=True,
        headers={"User-Agent": "Lexus-Personal-Hub/0.3"},
    )
    response.raise_for_status()
    return response.content


def _read_vendored_asset(name: str) -> bytes | None:
    path = _VENDOR_DIR / name
    if not path.is_file():
        return None
    return path.read_bytes()


def _asset_response(name: str, media_type: str) -> Response:
    content = _read_vendored_asset(name)
    if content is not None:
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=604800, immutable",
                "X-Lexus-Asset-Source": "vendored",
            },
        )

    # Development/source installs may not have the Docker-vendored assets.
    # Keep a network fallback for those environments, but production Docker
    # should normally serve from /app/vendor without any runtime CDN request.
    try:
        content = _download_asset(name)
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Lexus-Asset-Source": "network-fallback",
            },
        )
    except httpx.HTTPError as exc:
        return Response(
            content=f"/* MapLibre asset unavailable: {type(exc).__name__} */\n",
            status_code=502,
            media_type=media_type,
            headers={
                "Cache-Control": "no-store",
                "X-Lexus-Asset-Source": "unavailable",
            },
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
