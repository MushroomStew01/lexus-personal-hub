from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from lexus_hub.garage_v2 import garage_v2
from lexus_hub.map_assets import MapAssetProxyMiddleware


def test_garage_uses_same_origin_map_assets_and_replay_controls():
    response = garage_v2()
    html = response.body.decode("utf-8")

    assert '/vendor/maplibre-gl.css' in html
    assert '/vendor/maplibre-gl.js' in html
    assert '/map-fallback.js' in html
    assert 'Play replay' in html
    assert 'Center on Lexus' in html
    assert 'tile.openstreetmap.org' in html
    assert '/api/trips/${id}/replay' in html


def test_map_asset_middleware_rewrites_dashboard_cdn_links():
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return (
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/'
            'maplibre-gl@5.24.0/dist/maplibre-gl.css">'
            '<script src="https://cdn.jsdelivr.net/npm/'
            'maplibre-gl@5.24.0/dist/maplibre-gl.js"></script>'
        )

    app.add_middleware(MapAssetProxyMiddleware)
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert '/vendor/maplibre-gl.css' in response.text
    assert '/vendor/maplibre-gl.js' in response.text
    assert '/map-fallback.js' in response.text
    assert 'cdn.jsdelivr.net' not in response.text
