from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from lexus_hub.stability import StabilityMiddleware


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/app", response_class=HTMLResponse)
    def mobile():
        return "<html><body><main class='shell'>2026-08-15T10:31:34-04:00</main></body></html>"

    @app.get("/garage", response_class=HTMLResponse)
    def garage():
        return "<html><body><div id='replay-meta'>2026-08-15T10:21:34-04:00</div></body></html>"

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    app.add_middleware(StabilityMiddleware)
    return app


def test_stability_patch_is_injected_into_mobile_and_garage():
    client = TestClient(_app())
    for path in ("/app", "/garage"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="lexus-stability-css"' in response.text
        assert 'id="lexus-stability-js"' in response.text
        assert "Open Home LAN in Safari" in response.text
        assert response.headers["cache-control"] == "no-cache"


def test_stability_middleware_does_not_touch_api_responses():
    response = TestClient(_app()).get("/api/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "lexus-stability-js" not in response.text
