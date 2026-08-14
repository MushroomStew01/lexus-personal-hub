"""Resilience helpers for trip diagnostics and dashboard route rendering."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .db import init_db, session_scope
from .storage import trip_diagnostics

router = APIRouter(tags=["resilience"])

_MAP_SCRIPT_TAG = (
    '<script src="https://cdn.jsdelivr.net/npm/maplibre-gl@6.3.0/dist/maplibre-gl.js"></script>'
)
_FALLBACK_SCRIPT_TAG = '<script src="/map-fallback.js"></script>'


@router.get("/api/trip-diagnostics")
def api_trip_diagnostics() -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return trip_diagnostics(session, settings)


@router.get("/map-fallback.js", include_in_schema=False)
def map_fallback_js() -> Response:
    script = r"""
(() => {
  if (window.maplibregl) return;

  const SVG_NS = 'http://www.w3.org/2000/svg';

  function makeSvg(tag, attrs = {}) {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }

  class FallbackPopup {
    setText(text) {
      this.text = text;
      return this;
    }
  }

  class FallbackMarker {
    constructor(options = {}) {
      this.color = options.color || '#8ecbff';
      this.coord = null;
      this.map = null;
      this.popup = null;
    }

    setLngLat(coord) {
      this.coord = coord;
      if (this.map) this.map._render();
      return this;
    }

    setPopup(popup) {
      this.popup = popup;
      return this;
    }

    addTo(map) {
      this.map = map;
      map._markers.push(this);
      map._render();
      return this;
    }

    remove() {
      if (!this.map) return this;
      this.map._markers = this.map._markers.filter(marker => marker !== this);
      this.map._render();
      this.map = null;
      return this;
    }
  }

  class FallbackBounds {
    constructor() {
      this.points = [];
    }

    extend(coord) {
      this.points.push(coord);
      return this;
    }
  }

  class FallbackMap {
    constructor(options = {}) {
      this.container = typeof options.container === 'string'
        ? document.getElementById(options.container)
        : options.container;
      this.sources = {};
      this._markers = [];
      this._loaded = true;
      this._renderBase();
    }

    _renderBase() {
      if (!this.container) return;
      this.container.innerHTML = '';
      this.container.style.position = 'relative';
      this.container.style.background = '#0d141b';
      const note = document.createElement('div');
      note.textContent = 'Fallback route view';
      note.style.cssText = [
        'position:absolute',
        'right:10px',
        'bottom:8px',
        'z-index:2',
        'font:11px system-ui,sans-serif',
        'color:#8ea0b2',
        'background:rgba(9,13,18,.82)',
        'padding:4px 7px',
        'border-radius:7px'
      ].join(';');
      this.container.appendChild(note);
    }

    addControl() {}

    once(event, callback) {
      if (event === 'load') window.setTimeout(callback, 0);
      return this;
    }

    loaded() {
      return this._loaded;
    }

    resize() {
      this._render();
    }

    getSource(id) {
      return this.sources[id] || null;
    }

    addSource(id, source) {
      const wrapper = {
        data: source.data,
        setData: data => {
          wrapper.data = data;
          this._render();
        }
      };
      this.sources[id] = wrapper;
    }

    addLayer() {
      this._render();
    }

    fitBounds() {
      this._render();
    }

    _routeCoords() {
      const source = this.sources['trip-route'];
      const coords = source?.data?.geometry?.coordinates;
      return Array.isArray(coords) ? coords : [];
    }

    _render() {
      if (!this.container) return;
      const coords = this._routeCoords();
      this._renderBase();
      if (!coords.length) return;

      const width = 1000;
      const height = 600;
      const padding = 70;
      const lons = coords.map(coord => Number(coord[0]));
      const lats = coords.map(coord => Number(coord[1]));
      const minLon = Math.min(...lons);
      const maxLon = Math.max(...lons);
      const minLat = Math.min(...lats);
      const maxLat = Math.max(...lats);
      const lonSpan = Math.max(0.00001, maxLon - minLon);
      const latSpan = Math.max(0.00001, maxLat - minLat);

      const project = coord => {
        const x = padding
          + ((Number(coord[0]) - minLon) / lonSpan) * (width - padding * 2);
        const y = height - padding
          - ((Number(coord[1]) - minLat) / latSpan) * (height - padding * 2);
        return [x, y];
      };

      const svg = makeSvg('svg', {
        viewBox: `0 0 ${width} ${height}`,
        width: '100%',
        height: '100%',
        preserveAspectRatio: 'xMidYMid meet'
      });
      svg.style.display = 'block';

      for (let x = 0; x <= width; x += 100) {
        svg.appendChild(makeSvg('line', {
          x1: x,
          y1: 0,
          x2: x,
          y2: height,
          stroke: '#18222d',
          'stroke-width': 2
        }));
      }
      for (let y = 0; y <= height; y += 100) {
        svg.appendChild(makeSvg('line', {
          x1: 0,
          y1: y,
          x2: width,
          y2: y,
          stroke: '#18222d',
          'stroke-width': 2
        }));
      }

      const points = coords.map(project).map(point => point.join(',')).join(' ');
      svg.appendChild(makeSvg('polyline', {
        points,
        fill: 'none',
        stroke: '#2789d8',
        'stroke-width': 10,
        'stroke-linejoin': 'round',
        'stroke-linecap': 'round'
      }));

      this._markers.forEach(marker => {
        if (!marker.coord) return;
        const [x, y] = project(marker.coord);
        const circle = makeSvg('circle', {
          cx: x,
          cy: y,
          r: 16,
          fill: marker.color,
          stroke: '#f6f7f9',
          'stroke-width': 5
        });
        if (marker.popup?.text) {
          const title = makeSvg('title');
          title.textContent = marker.popup.text;
          circle.appendChild(title);
        }
        svg.appendChild(circle);
      });

      this.container.insertBefore(svg, this.container.firstChild);
    }
  }

  class FallbackNavigationControl {}

  window.maplibregl = {
    Map: FallbackMap,
    Marker: FallbackMarker,
    Popup: FallbackPopup,
    LngLatBounds: FallbackBounds,
    NavigationControl: FallbackNavigationControl,
    __fallback: true
  };
})();
""".strip()
    return Response(
        content=script,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


class DashboardMapFallbackMiddleware(BaseHTTPMiddleware):
    """Inject the same-origin map shim after the optional MapLibre CDN script."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path != "/":
            return response
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode("utf-8", errors="replace")
        if _MAP_SCRIPT_TAG in text and _FALLBACK_SCRIPT_TAG not in text:
            text = text.replace(
                _MAP_SCRIPT_TAG,
                _MAP_SCRIPT_TAG + "\n" + _FALLBACK_SCRIPT_TAG,
                1,
            )

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=text,
            status_code=response.status_code,
            headers=headers,
            media_type="text/html",
        )
