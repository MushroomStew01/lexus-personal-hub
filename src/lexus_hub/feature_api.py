from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .config import get_settings
from .db import init_db, session_scope
from .insights import (
    add_maintenance_record,
    add_named_location_from_current,
    current_vehicle_location,
    fuel_analytics,
    maintenance_history,
    named_locations,
    trip_replay,
    vehicle_timeline,
    weekly_summary,
)

router = APIRouter(tags=["vehicle insights"])


class NamedLocationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    radius_m: float | None = Field(default=None, ge=25, le=5000)
    is_private: bool = False


class MaintenanceRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    odometer_km: float | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)
    next_due_km: float | None = Field(default=None, ge=0)


@router.get("/api/where")
def api_where() -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return current_vehicle_location(session, settings)


@router.get("/api/locations")
def api_locations() -> list[dict[str, object]]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return named_locations(session, settings)


@router.post("/api/locations/current", status_code=201)
def api_add_current_location(payload: NamedLocationRequest) -> dict[str, object]:
    settings = get_settings()
    if not settings.store_location:
        raise HTTPException(status_code=409, detail="Set STORE_LOCATION=true first.")
    init_db()
    try:
        with session_scope() as session:
            location = add_named_location_from_current(
                session,
                settings,
                name=payload.name,
                radius_m=payload.radius_m,
                is_private=payload.is_private,
            )
            return {
                "id": location.id,
                "name": location.name,
                "radius_m": location.radius_m,
                "is_private": location.is_private,
            }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/trips/{trip_id}/replay")
def api_trip_replay(trip_id: int) -> dict[str, object]:
    settings = get_settings()
    if not settings.store_location:
        raise HTTPException(status_code=409, detail="Set STORE_LOCATION=true first.")
    if not settings.show_exact_location:
        raise HTTPException(status_code=403, detail="Set SHOW_EXACT_LOCATION=true first.")
    init_db()
    with session_scope() as session:
        replay = trip_replay(session, settings, trip_id)
    if replay is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return replay


@router.get("/api/fuel/analytics")
def api_fuel_analytics() -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return fuel_analytics(session, settings)


@router.get("/api/timeline")
def api_timeline(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[dict[str, object]]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return vehicle_timeline(session, settings, limit=limit)


@router.get("/api/maintenance")
def api_maintenance(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[dict[str, object]]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return maintenance_history(session, settings, limit=limit)


@router.post("/api/maintenance", status_code=201)
def api_add_maintenance(payload: MaintenanceRequest) -> dict[str, object]:
    settings = get_settings()
    init_db()
    try:
        with session_scope() as session:
            record = add_maintenance_record(
                session,
                settings,
                kind=payload.kind,
                odometer_km=payload.odometer_km,
                cost=payload.cost,
                notes=payload.notes,
                next_due_km=payload.next_due_km,
            )
            return {
                "id": record.id,
                "kind": record.kind,
                "odometer_km": record.odometer_km,
                "cost": record.cost,
                "next_due_km": record.next_due_km,
            }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/weekly")
def api_weekly() -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return weekly_summary(session, settings)


@router.get("/garage", response_class=HTMLResponse)
def garage() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lexus Garage · Personal Hub</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/maplibre-gl@6.3.0/dist/maplibre-gl.css">
<style>
:root{--bg:#090d12;--panel:#121a23;--line:#283442;--text:#f6f7f9;--muted:#8ea0b2;
--accent:#8ecbff;--good:#47d18c;--bad:#ff6b6b}*{box-sizing:border-box}body{margin:0;
background:radial-gradient(circle at top right,#172331,#090d12 35%);color:var(--text);
font-family:Inter,system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:32px 20px 70px}
a{color:var(--accent);text-decoration:none}header{display:flex;justify-content:space-between;
align-items:end;gap:18px;margin-bottom:18px}h1{margin:2px 0;font-size:2.2rem}h2{font-size:1rem;
margin:0 0 12px}.kicker,.muted{color:var(--muted);font-size:.78rem}.grid{display:grid;gap:14px}
.cards{grid-template-columns:repeat(3,1fr)}.panel{background:linear-gradient(180deg,#151e28,#111820);
border:1px solid var(--line);border-radius:18px;padding:18px;min-width:0}.metric{font-size:1.6rem;
font-weight:750;margin-top:6px}.row{display:flex;justify-content:space-between;gap:12px;padding:8px 0;
border-bottom:1px solid rgba(142,160,178,.12)}.row:last-child{border-bottom:0}.wide{grid-column:1/-1}
#park-map,#trip-map{height:360px;border-radius:14px;overflow:hidden;border:1px solid var(--line);
background:#0d141b}.trip-list{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}button,input{
font:inherit}button{border:1px solid #38516a;background:#162535;color:#a9d8ff;border-radius:9px;
padding:7px 10px;cursor:pointer}button:hover{background:#1e3247}input{background:#0d141b;color:var(--text);
border:1px solid var(--line);border-radius:9px;padding:8px}.form{display:flex;gap:8px;flex-wrap:wrap;
margin-top:12px}.form input[type=text],.form input[type=number]{min-width:130px;flex:1}.timeline-item{
padding:9px 0;border-bottom:1px solid rgba(142,160,178,.12)}#replay-slider{width:100%;margin-top:12px}
.replay-meta{display:flex;gap:18px;flex-wrap:wrap;margin-top:8px;color:var(--muted);font-size:.82rem}
@media(max-width:900px){.cards{grid-template-columns:1fr 1fr}}@media(max-width:620px){.cards{
grid-template-columns:1fr}header{align-items:flex-start;flex-direction:column}#park-map,#trip-map{height:300px}}
</style>
</head>
<body><main>
<header><div><div class="kicker">Lexus Personal Hub · Garage</div><h1>Driving intelligence</h1>
<div class="muted">Trips, locations, fuel, timeline, maintenance, and weekly stats.</div></div>
<a href="/">← Vehicle dashboard</a></header>
<section class="grid cards">
<article class="panel"><h2>Where's my Lexus?</h2><div id="where-main" class="metric">Loading…</div>
<div id="where-detail" class="muted"></div></article>
<article class="panel"><h2>Fuel analytics</h2><div id="fuel-main" class="metric">Loading…</div>
<div id="fuel-detail" class="muted"></div></article>
<article class="panel"><h2>Last 7 days</h2><div id="week-main" class="metric">Loading…</div>
<div id="week-detail" class="muted"></div></article>
<article class="panel wide"><h2>Parking map</h2><div id="park-map"></div></article>
<article class="panel wide"><h2>Trip replay</h2><div id="trip-list" class="trip-list"></div>
<div id="trip-map"></div><input id="replay-slider" type="range" min="0" max="0" value="0" disabled>
<div id="replay-meta" class="replay-meta"><span>Select a trip with GPS data.</span></div></article>
<article class="panel"><h2>Named locations</h2><div id="locations"></div>
<form id="location-form" class="form"><input id="location-name" type="text" placeholder="Home / Work" required>
<input id="location-radius" type="number" min="25" max="5000" value="250" aria-label="Radius metres">
<label class="muted"><input id="location-private" type="checkbox"> private</label><button>Save current</button></form></article>
<article class="panel"><h2>Maintenance</h2><div id="maintenance"></div>
<form id="maintenance-form" class="form"><input id="maintenance-kind" type="text" placeholder="Oil change" required>
<input id="maintenance-cost" type="number" min="0" step="0.01" placeholder="Cost">
<input id="maintenance-next" type="number" min="0" step="1" placeholder="Next due km"><button>Log</button></form></article>
<article class="panel"><h2>Vehicle timeline</h2><div id="timeline"></div></article>
</section>
</main>
<script src="https://cdn.jsdelivr.net/npm/maplibre-gl@6.3.0/dist/maplibre-gl.js"></script>
<script>
const rasterStyle={version:8,sources:{osm:{type:'raster',tiles:[
'https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap'}},
layers:[{id:'osm',type:'raster',source:'osm'}]};
const getJSON=async url=>{const r=await fetch(url);if(!r.ok)throw new Error(await r.text());return r.json()};
let parkMap=null,parkMarker=null,tripMap=null,replayMarker=null,replayPoints=[];
function fmt(v,s=''){return v===null||v===undefined?'—':`${Number(v).toLocaleString()}${s}`}
async function loadWhere(){try{const d=await getJSON('/api/where');
document.querySelector('#where-main').textContent=d.ready?(d.label||'Unknown location'):'No location';
document.querySelector('#where-detail').textContent=d.ready?`Fuel ${fmt(d.fuel_percent,'%')} · Range ${fmt(d.range_km,' km')} · ${d.parked_since?'Parked since '+d.parked_since:'Last '+(d.observed_at||'—')}`:'Waiting for GPS';
if(d.latitude!==undefined&&d.longitude!==undefined){const c=[d.longitude,d.latitude];if(!parkMap){
parkMap=new maplibregl.Map({container:'park-map',style:rasterStyle,center:c,zoom:14});
parkMap.addControl(new maplibregl.NavigationControl(),'top-right');parkMarker=new maplibregl.Marker().setLngLat(c).addTo(parkMap)}
else{parkMarker.setLngLat(c);parkMap.easeTo({center:c,zoom:14})}}}catch(e){document.querySelector('#where-main').textContent='Unavailable'}}
async function loadFuel(){const d=await getJSON('/api/fuel/analytics');const econ=d.average_l_per_100km;
document.querySelector('#fuel-main').textContent=econ===null||econ===undefined?'Need 2 fill-ups':`${econ} L/100 km`;
document.querySelector('#fuel-detail').textContent=`30d: $${Number(d.spend_30d||0).toFixed(2)} · ${d.liters_30d||0} L · ${d.average_cost_per_km===null?'—':'$'+d.average_cost_per_km+'/km'}`}
async function loadWeekly(){const d=await getJSON('/api/weekly');document.querySelector('#week-main').textContent=`${d.distance_km||0} km`;
document.querySelector('#week-detail').textContent=`${d.trip_count||0} trips · avg ${d.average_trip_km||0} km · longest ${d.longest_trip_km||0} km`}
async function loadLocations(){const d=await getJSON('/api/locations');document.querySelector('#locations').innerHTML=d.length?d.map(x=>`<div class="row"><span>${x.name}</span><span class="muted">${x.radius_m} m${x.is_private?' · private':''}</span></div>`).join(''):'<div class="muted">No named locations yet.</div>'}
async function loadMaintenance(){const d=await getJSON('/api/maintenance?limit=6');document.querySelector('#maintenance').innerHTML=d.length?d.map(x=>`<div class="row"><span>${x.kind}</span><span class="muted">${x.odometer_km===null?'—':x.odometer_km+' km'}</span></div>`).join(''):'<div class="muted">No maintenance records yet.</div>'}
async function loadTimeline(){const d=await getJSON('/api/timeline?limit=10');document.querySelector('#timeline').innerHTML=d.length?d.map(x=>`<div class="timeline-item"><div>${x.text}</div><div class="muted">${x.at}</div></div>`).join(''):'<div class="muted">No events yet.</div>'}
async function loadTrips(){const d=await getJSON('/api/trips?limit=8');const root=document.querySelector('#trip-list');root.innerHTML='';d.forEach(t=>{const b=document.createElement('button');b.textContent=`${t.start_label||'Start'} → ${t.end_label||'End'} · ${t.distance_km} km`;b.disabled=!t.has_route;b.onclick=()=>showTrip(t.id);root.appendChild(b)});if(!d.length)root.innerHTML='<span class="muted">No trips yet.</span>'}
function setReplay(i){if(!replayPoints.length)return;const p=replayPoints[i];const c=[p.longitude,p.latitude];if(replayMarker)replayMarker.setLngLat(c);document.querySelector('#replay-meta').innerHTML=`<span>${p.observed_at||'—'}</span><span>Speed ${fmt(p.speed_kph,' km/h')}</span><span>Fuel ${fmt(p.fuel_percent,'%')}</span><span>Odo ${fmt(p.odometer_km,' km')}</span>`}
async function showTrip(id){const d=await getJSON(`/api/trips/${id}/route`);const coords=(d.points||[]).map(p=>[p.longitude,p.latitude]);replayPoints=d.replay||[];
if(!tripMap){tripMap=new maplibregl.Map({container:'trip-map',style:rasterStyle,center:coords[0]||[-80.49,43.45],zoom:12});tripMap.addControl(new maplibregl.NavigationControl(),'top-right');tripMap.on('load',()=>drawTrip(coords))}else drawTrip(coords);
const slider=document.querySelector('#replay-slider');slider.max=Math.max(0,replayPoints.length-1);slider.value=0;slider.disabled=replayPoints.length<2;slider.oninput=e=>setReplay(Number(e.target.value));if(replayPoints.length){if(!replayMarker)replayMarker=new maplibregl.Marker({color:'#8ecbff'}).setLngLat([replayPoints[0].longitude,replayPoints[0].latitude]).addTo(tripMap);setReplay(0)}}
function drawTrip(coords){if(!tripMap||!coords.length)return;const data={type:'Feature',geometry:{type:'LineString',coordinates:coords}};const existing=tripMap.getSource('trip-line');if(existing)existing.setData(data);else{tripMap.addSource('trip-line',{type:'geojson',data});tripMap.addLayer({id:'trip-line',type:'line',source:'trip-line',paint:{'line-color':'#8ecbff','line-width':5}})}const bounds=new maplibregl.LngLatBounds();coords.forEach(c=>bounds.extend(c));tripMap.fitBounds(bounds,{padding:55,maxZoom:15})}
document.querySelector('#location-form').onsubmit=async e=>{e.preventDefault();const payload={name:document.querySelector('#location-name').value,radius_m:Number(document.querySelector('#location-radius').value),is_private:document.querySelector('#location-private').checked};const r=await fetch('/api/locations/current',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!r.ok){alert(await r.text());return}document.querySelector('#location-name').value='';await loadLocations();await loadWhere()};
document.querySelector('#maintenance-form').onsubmit=async e=>{e.preventDefault();const cost=document.querySelector('#maintenance-cost').value;const due=document.querySelector('#maintenance-next').value;const payload={kind:document.querySelector('#maintenance-kind').value,cost:cost?Number(cost):null,next_due_km:due?Number(due):null};const r=await fetch('/api/maintenance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!r.ok){alert(await r.text());return}e.target.reset();await loadMaintenance();await loadTimeline()};
Promise.all([loadWhere(),loadFuel(),loadWeekly(),loadLocations(),loadMaintenance(),loadTimeline(),loadTrips()]);
</script>
</body></html>"""
    )
