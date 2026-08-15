"""Trip-focused stability middleware for the mobile Lexus Hub."""

from __future__ import annotations

import json
import re
from collections import OrderedDict

import httpx
from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings

_ROUTE_RE = re.compile(r"^/api/trips/(\d+)/route$")
_ROUTE_CACHE: OrderedDict[tuple[tuple[float, float], ...], list[list[float]]] = OrderedDict()
_ROUTE_CACHE_MAX = 128

_MOBILE_PATCH = r"""
<style id="lexus-trip-stability-css">
.bottom-nav{grid-template-columns:repeat(3,1fr)!important}
</style>
<script id="lexus-trip-stability-js">
(()=>{
  const qsa=(selector,root=document)=>[...root.querySelectorAll(selector)];
  let applying=false;

  const removeGarage=()=>{
    qsa('a[href="/garage"]').forEach(el=>el.remove());
    qsa('a,button').forEach(el=>{
      const text=(el.textContent||'').trim().toLowerCase();
      if(text==='garage & replay'||text==='open full replay')el.remove();
    });
  };

  const renamePeak=()=>{
    qsa('.trip-stat-v2 span,.summary-stat span').forEach(el=>{
      if((el.textContent||'').trim().toLowerCase()==='sampled peak')el.textContent='Peak estimate';
    });
  };

  const renderPhysicalLocation=async()=>{
    const target=document.querySelector('#where-main');
    if(!target)return;
    try{
      const response=await fetch('/api/location/address',{cache:'no-store'});
      if(!response.ok)return;
      const data=await response.json();
      if(data.ready&&data.estimated_address)target.textContent=data.estimated_address;
    }catch(_){ }
  };

  const renderPhysicalTimeline=async()=>{
    const root=document.querySelector('#activity');
    if(!root)return;
    try{
      const response=await fetch('/api/timeline/physical?limit=6',{cache:'no-store'});
      if(!response.ok)return;
      const items=await response.json();
      root.replaceChildren();
      items.forEach(item=>{
        const row=document.createElement('div');row.className='timeline-row';
        const text=document.createElement('div');text.className='timeline-text';text.textContent=item.text||'Vehicle event';
        const time=document.createElement('div');time.className='timeline-time';
        if(item.at){
          const d=new Date(item.at);
          time.textContent=Number.isNaN(d.getTime())?item.at:d.toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).replace(',',' at');
        }
        row.append(text,time);root.appendChild(row);
      });
    }catch(_){ }
  };

  const apply=()=>{
    if(applying)return;
    applying=true;
    removeGarage();renamePeak();
    Promise.allSettled([renderPhysicalLocation(),renderPhysicalTimeline()]).finally(()=>{applying=false});
  };

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply,{once:true});else apply();
  let timer=null;
  new MutationObserver(()=>{
    clearTimeout(timer);timer=setTimeout(()=>{removeGarage();renamePeak();renderPhysicalLocation()},80);
  }).observe(document.documentElement,{subtree:true,childList:true,characterData:true});
  setInterval(()=>{renderPhysicalLocation();renderPhysicalTimeline()},60000);
})();
</script>
""".strip()


def _sample_waypoints(points: list[dict[str, object]], maximum: int = 25) -> list[dict[str, object]]:
    if len(points) <= maximum:
        return points
    sampled = [points[0]]
    step = (len(points) - 1) / (maximum - 1)
    for index in range(1, maximum - 1):
        sampled.append(points[round(index * step)])
    sampled.append(points[-1])
    return sampled


def _route_key(points: list[dict[str, object]]) -> tuple[tuple[float, float], ...]:
    return tuple(
        (
            round(float(point["longitude"]), 5),
            round(float(point["latitude"]), 5),
        )
        for point in points
    )


async def _road_geometry(points: list[dict[str, object]]) -> list[list[float]] | None:
    if len(points) < 2:
        return None
    waypoints = _sample_waypoints(points)
    key = _route_key(waypoints)
    cached = _ROUTE_CACHE.get(key)
    if cached is not None:
        _ROUTE_CACHE.move_to_end(key)
        return cached

    settings = get_settings()
    coordinates = ";".join(
        f"{float(point['longitude'])},{float(point['latitude'])}" for point in waypoints
    )
    url = f"{settings.map_router_url.rstrip('/')}/route/v1/driving/{coordinates}"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                params={
                    "overview": "full",
                    "geometries": "geojson",
                    "steps": "false",
                    "continue_straight": "true",
                },
                headers={"User-Agent": "Lexus-Personal-Hub/0.3"},
            )
        response.raise_for_status()
        payload = response.json()
        geometry = payload.get("routes", [{}])[0].get("geometry", {}).get("coordinates")
        if not isinstance(geometry, list) or len(geometry) < 2:
            return None
        normalized = [
            [float(coord[0]), float(coord[1])]
            for coord in geometry
            if isinstance(coord, list) and len(coord) >= 2
        ]
        if len(normalized) < 2:
            return None
        _ROUTE_CACHE[key] = normalized
        _ROUTE_CACHE.move_to_end(key)
        while len(_ROUTE_CACHE) > _ROUTE_CACHE_MAX:
            _ROUTE_CACHE.popitem(last=False)
        return normalized
    except (httpx.HTTPError, ValueError, TypeError, IndexError, KeyError):
        return None


class TripExperienceMiddleware(BaseHTTPMiddleware):
    """Remove Garage and road-snap inline trip routes without changing stored GPS."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/garage":
            return RedirectResponse(url="/app#trips", status_code=307)

        response = await call_next(request)

        if path == "/manifest.webmanifest" and "json" in response.headers.get("content-type", ""):
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            try:
                payload = json.loads(body)
                shortcuts = payload.get("shortcuts")
                if isinstance(shortcuts, list):
                    payload["shortcuts"] = [
                        item
                        for item in shortcuts
                        if not isinstance(item, dict) or item.get("url") != "/garage"
                    ]
                body = json.dumps(payload, separators=(",", ":")).encode()
            except (json.JSONDecodeError, TypeError):
                pass
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type="application/manifest+json",
            )

        if _ROUTE_RE.match(path) and response.status_code == 200:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            try:
                payload = json.loads(body)
                points = payload.get("points")
                if isinstance(points, list) and len(points) >= 2:
                    road = await _road_geometry(points)
                    if road:
                        payload["raw_points"] = points
                        payload["points"] = [
                            {"longitude": lon, "latitude": lat, "observed_at": None}
                            for lon, lat in road
                        ]
                        payload["route_source"] = "road_router"
                    else:
                        payload["route_source"] = "stored_gps"
                body = json.dumps(payload, separators=(",", ":")).encode()
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type="application/json",
            )

        if path == "/app" and "text/html" in response.headers.get("content-type", ""):
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            text = body.decode("utf-8", errors="replace")
            if "lexus-trip-stability-js" not in text and "</body>" in text:
                text = text.replace("</body>", f"{_MOBILE_PATCH}</body>", 1)
            headers = dict(response.headers)
            headers.pop("content-length", None)
            headers["Cache-Control"] = "no-cache"
            return Response(
                content=text,
                status_code=response.status_code,
                headers=headers,
                media_type="text/html",
            )

        return response
