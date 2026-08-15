from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from lexus_hub.mobile_app_v2 import GarageReturnLinkMiddleware
from lexus_hub.mobile_app_v2 import router as mobile_app_v2_router
from lexus_hub.pwa import router as pwa_router


def test_mobile_v2_wins_app_route_and_has_persistent_navigation():
    app = FastAPI()
    app.include_router(mobile_app_v2_router)
    app.include_router(pwa_router)
    client = TestClient(app)

    page = client.get("/app")
    assert page.status_code == 200
    assert "Overview" in page.text
    assert "Status" in page.text
    assert "Recent trips" in page.text
    assert 'href="/garage"' in page.text
    assert 'id="vehicle-refresh-button"' in page.text
    assert 'id="connection-card"' in page.text
    assert 'id="view-status"' in page.text
    assert 'id="view-trips"' in page.text
    assert "Tire pressure" in page.text
    assert "Distance to empty" in page.text


def test_garage_return_link_points_back_to_mobile_app():
    app = FastAPI()

    @app.get("/garage", response_class=HTMLResponse)
    def garage() -> str:
        return '<html><body><a href="/">← Vehicle dashboard</a></body></html>'

    app.add_middleware(GarageReturnLinkMiddleware)
    client = TestClient(app)

    page = client.get("/garage")
    assert page.status_code == 200
    assert 'href="/app#overview">← Lexus app</a>' in page.text
    assert 'href="/">← Vehicle dashboard</a>' not in page.text
