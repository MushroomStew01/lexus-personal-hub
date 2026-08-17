"""Trip-focused stability middleware for the mobile Lexus Hub."""

from __future__ import annotations

import json
import re
from collections import OrderedDict

import httpx
from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .db import init_db, session_scope
from .mobile_enhancements import _estimated_address
from .models import Snapshot
from .storage import primary_vehicle

_ROUTE_RE = re.compile(r"^/api/trips/(\d+)/route$")
_ROUTE_CACHE: OrderedDict[tuple[tuple[float, float], ...], list[list[float]]] = OrderedDict()
_ROUTE_CACHE_MAX = 128

_MOBILE_PATCH = r"""
<style id="lexus-trip-stability-css">
.bottom-nav{grid-template-columns:repeat(3,1fr)!important}
.inline-replay{margin-top:10px;border-top:1px solid #243442;padding-top:10px}
.inline-replay-controls{display:grid;grid-template-columns:auto 1fr auto;gap:9px;align-items:center}
.replay-play{border:1px solid #38516a;background:#162535;color:#a9d8ff;border-radius:10px;padding:8px 12px;font:inherit;font-size:.72rem}
.replay-slider{width:100%;accent-color:#79c6ff}
.replay-speed{border:1px solid #2a3b4b;background:#0d151d;color:#dce8f2;border-radius:9px;padding:7px;font:inherit;font-size:.68rem}
.replay-meta-inline{display:flex;gap:10px;flex-wrap:wrap;color:#91a3b5;font-size:.62rem;margin-top:7px;min-height:17px}
.parking-map-inline{height:220px;border:1px solid #293b4b;border-radius:14px;margin-top:13px;background:#081018;overflow:hidden}
.parking-map-note{color:#91a3b5;font-size:.62rem;margin-top:7px;line-height:1.4}
.replay-car-marker{width:20px;height:20px;border-radius:50%;background:#79c6ff;border:3px solid #f7f8fa;box-shadow:0 0 0 4px rgba(121,198,255,.2),0 4px 12px rgba(0,0,0,.4)}
</style>
<script id="lexus-trip-stability-js">
(()=>{
  const qsa=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const rasterStyle={version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap contributors'}},layers:[{id:'osm',type:'raster',source:'osm'}]};
  let applying=false,tripListCache=null,parkingMap=null,parkingMarker=null,parkingMapLoading=false;
  const replayStates=new WeakMap();

  const getJSON=async url=>{const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw new Error(await r.text());return r.json()};
  const fmt=(value,suffix='')=>value===null||value===undefined?'—':`${value}${suffix}`;

  const removeGarage=()=>{
    qsa('a[href="/garage"]').forEach(el=>el.remove());
    qsa('a,button').forEach(el=>{
      const text=(el.textContent||'').trim().toLowerCase();
      if(text==='garage & replay'||text==='open full replay'||text==='open parking map')el.remove();
    });
  };

  const renamePeak=()=>{
    qsa('.trip-stat-v2 span,.summary-stat span').forEach(el=>{
      const text=(el.textContent||'').trim().toLowerCase();
      if(text==='sampled peak'||text==='peak estimate'||text==='top speed')el.textContent='Top speed';
    });
  };

  const renderPhysicalLocation=async()=>{
    const target=document.querySelector('#where-main');
    if(!target)return;
    try{
      const data=await getJSON('/api/location/address');
      if(data.ready&&data.estimated_address)target.textContent=data.estimated_address;
    }catch(_){ }
  };

  const renderPhysicalTimeline=async()=>{
    const root=document.querySelector('#activity');
    if(!root)return;
    try{
      const items=await getJSON('/api/timeline/physical?limit=6');
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

  function routePosition(coords,progress){
    if(!coords.length)return null;if(coords.length===1)return coords[0];
    const lengths=[];let total=0;
    for(let i=1;i<coords.length;i++){
      const dx=coords[i][0]-coords[i-1][0],dy=coords[i][1]-coords[i-1][1];
      const len=Math.hypot(dx,dy);lengths.push(len);total+=len;
    }
    if(total<=0)return coords[0];
    let target=Math.max(0,Math.min(1,progress))*total;
    for(let i=0;i<lengths.length;i++){
      if(target<=lengths[i]){
        const ratio=lengths[i]<=0?0:target/lengths[i];
        return [coords[i][0]+(coords[i+1][0]-coords[i][0])*ratio,coords[i][1]+(coords[i+1][1]-coords[i][1])*ratio];
      }
      target-=lengths[i];
    }
    return coords.at(-1);
  }

  function replayTelemetry(replay,progress){
    if(!replay?.length)return null;
    const index=Math.min(replay.length-1,Math.round(Math.max(0,Math.min(1,progress))*(replay.length-1)));
    return replay[index];
  }

  async function initReplayMap(card,state){
    if(state.map)return;
    const oldBox=card.querySelector('.trip-map');if(!oldBox)throw new Error('Map unavailable');
    const box=oldBox.cloneNode(false);oldBox.replaceWith(box);
    const data=state.data||await getJSON(`/api/trips/${state.tripId}/route`);state.data=data;
    const coords=(data.points||[]).map(p=>[Number(p.longitude),Number(p.latitude)]).filter(c=>Number.isFinite(c[0])&&Number.isFinite(c[1]));
    if(coords.length<2||typeof maplibregl==='undefined')throw new Error('Route unavailable');
    state.coords=coords;box.innerHTML='';
    const map=new maplibregl.Map({container:box,style:rasterStyle,center:coords[0],zoom:13,minZoom:2,maxZoom:19});
    map.addControl(new maplibregl.NavigationControl(),'top-right');
    await new Promise(resolve=>map.on('load',resolve));
    map.addSource('route',{type:'geojson',data:{type:'Feature',properties:{},geometry:{type:'LineString',coordinates:coords}}});
    map.addLayer({id:'route',type:'line',source:'route',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#55adff','line-width':5}});
    new maplibregl.Marker({color:'#49d690'}).setLngLat(coords[0]).addTo(map);
    new maplibregl.Marker({color:'#ff6969'}).setLngLat(coords.at(-1)).addTo(map);
    const car=document.createElement('div');car.className='replay-car-marker';
    state.marker=new maplibregl.Marker({element:car}).setLngLat(coords[0]).addTo(map);
    const bounds=new maplibregl.LngLatBounds();coords.forEach(c=>bounds.extend(c));map.fitBounds(bounds,{padding:35,maxZoom:16,duration:0});
    state.map=map;state.replay=data.replay||[];
  }

  function setReplayProgress(card,state,progress){
    progress=Math.max(0,Math.min(1,progress));state.progress=progress;
    if(state.slider)state.slider.value=String(Math.round(progress*1000));
    const coord=routePosition(state.coords||[],progress);if(coord&&state.marker)state.marker.setLngLat(coord);
    const sample=replayTelemetry(state.replay,progress);
    if(state.meta){
      state.meta.replaceChildren();
      const values=sample?[sample.observed_at?new Date(sample.observed_at).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}):null,fmt(sample.speed_kph,' km/h'),fmt(sample.fuel_percent,'%'),fmt(sample.odometer_km,' km')]:[];
      values.filter(Boolean).forEach(value=>{const span=document.createElement('span');span.textContent=value;state.meta.appendChild(span)});
    }
  }

  function stopReplay(state){
    if(state.frame)cancelAnimationFrame(state.frame);state.frame=null;state.playing=false;if(state.play)state.play.textContent='Play';
  }

  async function startReplay(card,state){
    await initReplayMap(card,state);
    if(state.playing){stopReplay(state);return}
    state.playing=true;state.play.textContent='Pause';
    if(state.progress>=.999)state.progress=0;
    const rate=Number(state.speed.value)||1,baseDuration=30000,duration=baseDuration/rate,start=performance.now()-state.progress*duration;
    const tick=now=>{
      if(!state.playing)return;
      const progress=Math.min(1,(now-start)/duration);setReplayProgress(card,state,progress);
      if(progress>=1){stopReplay(state);return}state.frame=requestAnimationFrame(tick);
    };
    state.frame=requestAnimationFrame(tick);
  }

  async function decorateExpandedTrips(){
    const cards=qsa('#trips .trip-card');if(!cards.length)return;
    if(!tripListCache){try{tripListCache=await getJSON('/api/trips?limit=20')}catch(_){return}}
    cards.forEach((card,index)=>{
      if(!card.classList.contains('expanded')||card.querySelector('.inline-replay'))return;
      const trip=tripListCache[index];if(!trip?.id)return;
      const detail=card.querySelector('.trip-detail'),map=card.querySelector('.trip-map');if(!detail||!map)return;
      qsa('a,button',detail).forEach(el=>{if((el.textContent||'').trim().toLowerCase()==='open full replay')el.remove()});
      const wrap=document.createElement('div');wrap.className='inline-replay';
      const controls=document.createElement('div');controls.className='inline-replay-controls';
      const play=document.createElement('button');play.type='button';play.className='replay-play';play.textContent='Play';
      const slider=document.createElement('input');slider.type='range';slider.min='0';slider.max='1000';slider.value='0';slider.className='replay-slider';slider.setAttribute('aria-label','Trip replay position');
      const speed=document.createElement('select');speed.className='replay-speed';speed.setAttribute('aria-label','Replay speed');
      [1,2,4].forEach(v=>{const o=document.createElement('option');o.value=String(v);o.textContent=`${v}×`;speed.appendChild(o)});
      const meta=document.createElement('div');meta.className='replay-meta-inline';meta.textContent='Press Play to replay this trip.';
      controls.append(play,slider,speed);wrap.append(controls,meta);map.after(wrap);
      const state={tripId:trip.id,map:null,marker:null,coords:[],replay:[],progress:0,playing:false,frame:null,play,slider,speed,meta,data:null};replayStates.set(card,state);
      play.addEventListener('click',()=>startReplay(card,state).catch(()=>{meta.textContent='Replay unavailable for this trip.';stopReplay(state)}));
      slider.addEventListener('input',async()=>{stopReplay(state);try{await initReplayMap(card,state);setReplayProgress(card,state,Number(slider.value)/1000)}catch(_){meta.textContent='Replay unavailable for this trip.'}});
      speed.addEventListener('change',()=>{if(state.playing){stopReplay(state);startReplay(card,state)}});
    });
  }

  async function renderParkingMap(){
    const target=document.querySelector('#where-main');if(!target||parkingMap||parkingMapLoading)return;
    const card=target.closest('.card');if(!card)return;
    if(card.querySelector('#lexus-parking-map'))return;
    parkingMapLoading=true;
    try{
      const data=await getJSON('/api/location/parking-point');
      if(!data.ready||!Number.isFinite(Number(data.latitude))||!Number.isFinite(Number(data.longitude))||typeof maplibregl==='undefined')return;
      if(data.address)target.textContent=data.address;
      const box=document.createElement('div');box.id='lexus-parking-map';box.className='parking-map-inline';box.setAttribute('aria-label','Parked vehicle map');card.appendChild(box);
      const note=document.createElement('div');note.id='lexus-parking-map-note';note.className='parking-map-note';note.textContent='Last saved Lexus parking position.';card.appendChild(note);
      const center=[Number(data.longitude),Number(data.latitude)];
      parkingMap=new maplibregl.Map({container:box,style:rasterStyle,center,zoom:15.5,minZoom:2,maxZoom:19});parkingMap.addControl(new maplibregl.NavigationControl(),'top-right');
      parkingMarker=new maplibregl.Marker({color:'#79c6ff'}).setLngLat(center).addTo(parkingMap);
    }catch(_){
      document.querySelector('#lexus-parking-map')?.remove();
      document.querySelector('#lexus-parking-map-note')?.remove();
    }finally{
      parkingMapLoading=false;
    }
  }

  const apply=()=>{
    if(applying)return;applying=true;removeGarage();renamePeak();
    Promise.allSettled([renderPhysicalLocation(),renderPhysicalTimeline(),renderParkingMap(),decorateExpandedTrips()]).finally(()=>{applying=false});
  };

  document.addEventListener('click',event=>{if(event.target.closest('.trip-toggle'))setTimeout(()=>decorateExpandedTrips(),700)});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply,{once:true});else apply();
  let timer=null;
  new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(()=>{removeGarage();renamePeak();renderPhysicalLocation();renderParkingMap();decorateExpandedTrips()},120)}).observe(document.documentElement,{subtree:true,childList:true,characterData:true});
  setInterval(()=>{tripListCache=null;renderPhysicalLocation();renderPhysicalTimeline();renderParkingMap()},60000);
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


def _parking_payload() -> dict[str, object]:
    settings = get_settings()
    if not settings.store_location or not settings.show_exact_location:
        return {"ready": False, "reason": "Exact private location display is disabled."}
    init_db()
    with session_scope() as session:
        vehicle = primary_vehicle(session, settings)
        if vehicle is None:
            return {"ready": False, "reason": "No vehicle data."}
        latest = session.scalar(
            select(Snapshot)
            .where(
                Snapshot.vehicle_id == vehicle.id,
                Snapshot.latitude.is_not(None),
                Snapshot.longitude.is_not(None),
            )
            .order_by(Snapshot.observed_at.desc())
            .limit(1)
        )
        if latest is None or latest.latitude is None or latest.longitude is None:
            return {"ready": False, "reason": "No saved parking location."}
        latitude = float(latest.latitude)
        longitude = float(latest.longitude)
        speed = latest.speed_kph
    parked = speed is None or float(speed) <= settings.parking_speed_threshold_kph
    if not parked:
        return {"ready": False, "reason": "Vehicle is not parked."}
    return {
        "ready": True,
        "latitude": latitude,
        "longitude": longitude,
        "address": _estimated_address(settings, latitude, longitude),
    }


class TripExperienceMiddleware(BaseHTTPMiddleware):
    """Remove Garage, road-snap trip routes, and add private inline replay/location UI."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/garage":
            return RedirectResponse(url="/app#trips", status_code=307)
        if path == "/api/location/parking-point":
            return Response(
                content=json.dumps(_parking_payload(), separators=(",", ":")),
                media_type="application/json",
                headers={"Cache-Control": "no-store"},
            )

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
