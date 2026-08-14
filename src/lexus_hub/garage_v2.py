"""Improved Garage page with street maps and animated trip replay."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .config import get_settings

router = APIRouter(tags=["garage"])


@router.get("/garage", response_class=HTMLResponse)
def garage_v2() -> HTMLResponse:
    settings = get_settings()
    router_base = json.dumps(settings.map_router_url.rstrip("/"))
    html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lexus Garage · Personal Hub</title>
<link rel="stylesheet" href="/vendor/maplibre-gl.css">
<style>
:root{--bg:#090d12;--panel:#121a23;--line:#283442;--text:#f6f7f9;
--muted:#8ea0b2;--accent:#8ecbff;--good:#47d18c;--bad:#ff6b6b}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top right,
#172331,#090d12 35%);color:var(--text);font-family:Inter,system-ui,sans-serif}
main{max-width:1280px;margin:auto;padding:32px 20px 70px}a{color:var(--accent);
text-decoration:none}header{display:flex;justify-content:space-between;align-items:end;
gap:18px;margin-bottom:18px}h1{margin:2px 0;font-size:2.2rem}h2{font-size:1rem;
margin:0 0 12px}.kicker,.muted{color:var(--muted);font-size:.78rem}.grid{display:grid;
gap:14px}.cards{grid-template-columns:repeat(3,1fr)}.panel{background:linear-gradient(
180deg,#151e28,#111820);border:1px solid var(--line);border-radius:18px;padding:18px;
min-width:0}.metric{font-size:1.6rem;font-weight:750;margin-top:6px}.row{display:flex;
justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid
rgba(142,160,178,.12)}.row:last-child{border-bottom:0}.wide{grid-column:1/-1}
.map-shell{position:relative}.map{height:420px;border-radius:14px;overflow:hidden;
border:1px solid var(--line);background:#0d141b}.map-tools{display:flex;gap:8px;
flex-wrap:wrap;margin:0 0 10px}.map-note{color:var(--muted);font-size:.78rem;
margin-top:8px}.trip-list{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
button,input,select{font:inherit}button{border:1px solid #38516a;background:#162535;
color:#a9d8ff;border-radius:9px;padding:7px 10px;cursor:pointer}button:hover{
background:#1e3247}button.active{border-color:#d9ecff;color:white;box-shadow:
0 0 0 1px rgba(255,255,255,.35)}button:disabled{opacity:.45;cursor:not-allowed}
input,select{background:#0d141b;color:var(--text);border:1px solid var(--line);
border-radius:9px;padding:8px}.form{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.form input[type=text],.form input[type=number]{min-width:130px;flex:1}.timeline-item{
padding:9px 0;border-bottom:1px solid rgba(142,160,178,.12)}.replay-controls{
display:flex;align-items:center;gap:10px;margin-top:12px}.replay-controls input{flex:1;
min-width:140px;padding:0}.replay-meta{display:flex;gap:18px;flex-wrap:wrap;margin-top:8px;
color:var(--muted);font-size:.82rem}.status{color:var(--muted);font-size:.8rem}
.maplibregl-ctrl-group button{padding:0}.maplibregl-popup-content{color:#111}
@media(max-width:900px){.cards{grid-template-columns:1fr 1fr}}
@media(max-width:620px){.cards{grid-template-columns:1fr}header{align-items:flex-start;
flex-direction:column}.map{height:330px}.replay-controls{align-items:stretch;flex-wrap:wrap}
.replay-controls input{width:100%;flex-basis:100%}}
</style>
</head>
<body><main>
<header><div><div class="kicker">Lexus Personal Hub · Garage</div>
<h1>Driving intelligence</h1><div class="muted">Trips, locations, fuel, timeline,
maintenance, and weekly stats.</div></div><a href="/">← Vehicle dashboard</a></header>
<section class="grid cards">
<article class="panel"><h2>Where's my Lexus?</h2><div id="where-main" class="metric">
Loading…</div><div id="where-detail" class="muted"></div></article>
<article class="panel"><h2>Fuel analytics</h2><div id="fuel-main" class="metric">
Loading…</div><div id="fuel-detail" class="muted"></div></article>
<article class="panel"><h2>Last 7 days</h2><div id="week-main" class="metric">
Loading…</div><div id="week-detail" class="muted"></div></article>
<article class="panel wide"><h2>Parking map</h2>
<div class="map-tools"><button id="center-car" type="button">Center on Lexus</button>
<span id="park-status" class="status">Loading location…</span></div>
<div id="park-map" class="map"></div>
<div class="map-note">OpenStreetMap street labels · drag to pan · scroll or pinch to zoom.</div>
</article>
<article class="panel wide"><h2>Trip replay</h2>
<div id="trip-list" class="trip-list"></div><div id="trip-status" class="status">
Select a trip with GPS data.</div><div id="trip-map" class="map"></div>
<div class="replay-controls"><button id="replay-play" type="button" disabled>Play replay</button>
<select id="replay-speed" aria-label="Replay speed"><option value="1">1×</option>
<option value="2">2×</option><option value="4">4×</option></select>
<input id="replay-slider" type="range" min="0" max="1000" value="0" disabled></div>
<div id="replay-meta" class="replay-meta"><span>Select a trip with GPS data.</span></div>
</article>
<article class="panel"><h2>Named locations</h2><div id="locations"></div>
<form id="location-form" class="form"><input id="location-name" type="text"
placeholder="Home / Work" required><input id="location-radius" type="number" min="25"
max="5000" value="250" aria-label="Radius metres"><label class="muted">
<input id="location-private" type="checkbox"> private</label><button>Save current</button>
</form></article>
<article class="panel"><h2>Maintenance</h2><div id="maintenance"></div>
<form id="maintenance-form" class="form"><input id="maintenance-kind" type="text"
placeholder="Oil change" required><input id="maintenance-cost" type="number" min="0"
step="0.01" placeholder="Cost"><input id="maintenance-next" type="number" min="0"
step="1" placeholder="Next due km"><button>Log</button></form></article>
<article class="panel"><h2>Vehicle timeline</h2><div id="timeline"></div></article>
</section></main>
<script src="/vendor/maplibre-gl.js"></script>
<script src="/map-fallback.js"></script>
<script>
const routerBase=__ROUTER_BASE__;
const rasterStyle={version:8,sources:{osm:{type:'raster',tiles:[
'https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,
attribution:'© OpenStreetMap contributors'}},layers:[{id:'osm',type:'raster',source:'osm'}]};
const getJSON=async url=>{const r=await fetch(url,{headers:{Accept:'application/json'}});
if(!r.ok)throw new Error(await r.text());return r.json()};
let parkMap=null,parkMarker=null,parkCoord=null;
let tripMap=null,replayMarker=null,startMarker=null,endMarker=null;
let replayPoints=[],routeCoords=[],replayFrame=null,replayStartedAt=null,replayStartValue=0;
function fmt(v,s=''){return v===null||v===undefined?'—':`${Number(v).toLocaleString()}${s}`}
function isCoord(c){return Array.isArray(c)&&Number.isFinite(Number(c[0]))&&
Number.isFinite(Number(c[1]))}
function makeMap(container,center,zoom){
 const map=new maplibregl.Map({container,style:rasterStyle,center,zoom,minZoom:2,maxZoom:19});
 map.addControl(new maplibregl.NavigationControl(),'top-right');
 if(maplibregl.FullscreenControl)map.addControl(new maplibregl.FullscreenControl(),'top-right');
 if(maplibregl.ScaleControl){
  map.addControl(new maplibregl.ScaleControl({unit:'metric'}),'bottom-left');
 }
 return map;
}
function fitMap(map,coords,maxZoom=16){
 if(!coords.length)return;
 const b=new maplibregl.LngLatBounds();
 coords.forEach(c=>b.extend(c));map.fitBounds(b,{padding:65,maxZoom,duration:500})
}
function haversine(a,b){const r=6371000,toRad=x=>x*Math.PI/180;const p1=toRad(a[1]);
const p2=toRad(b[1]);const dp=toRad(b[1]-a[1]);const dl=toRad(b[0]-a[0]);
const q=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
return 2*r*Math.asin(Math.min(1,Math.sqrt(q)))}
function coordAtFraction(coords,f){if(coords.length<2)return coords[0]||null;
const lengths=[0];for(let i=1;i<coords.length;i++)lengths.push(lengths[i-1]+haversine(
coords[i-1],coords[i]));const total=lengths[lengths.length-1]||1;const target=total*f;
let i=1;while(i<lengths.length&&lengths[i]<target)i++;i=Math.min(i,lengths.length-1);
const seg=Math.max(1,lengths[i]-lengths[i-1]);const t=(target-lengths[i-1])/seg;
return [coords[i-1][0]+(coords[i][0]-coords[i-1][0])*t,
coords[i-1][1]+(coords[i][1]-coords[i-1][1])*t]}
function addLine(map,id,coords,color,width=5){const data={type:'Feature',properties:{},
geometry:{type:'LineString',coordinates:coords}};const source=map.getSource(id);
if(source)source.setData(data);else{map.addSource(id,{type:'geojson',data});map.addLayer({id,
type:'line',source:id,layout:{'line-join':'round','line-cap':'round'},paint:{
'line-color':color,'line-width':width,'line-opacity':.92}})}}
function mapIsReady(map){return map&&typeof map.loaded==='function'&&map.loaded()}
async function roadRoute(stored){if(stored.length<2)return stored;const max=20;let points=stored;
if(stored.length>max){points=[stored[0]];const step=(stored.length-1)/(max-1);
for(let i=1;i<max-1;i++)points.push(stored[Math.round(i*step)]);points.push(stored.at(-1))}
try{const encoded=points.map(c=>`${c[0]},${c[1]}`).join(';');const url=
`${routerBase}/route/v1/driving/${encoded}?overview=full&geometries=geojson&steps=false`;
const r=await fetch(url);const d=await r.json();const coords=d?.routes?.[0]?.geometry?.coordinates;
return r.ok&&Array.isArray(coords)&&coords.length>1?coords:stored}catch(_e){return stored}}
async function loadWhere(){const main=document.querySelector('#where-main');const detail=
document.querySelector('#where-detail');const status=document.querySelector('#park-status');
try{const d=await getJSON('/api/where');main.textContent=d.ready?(d.label||'Unknown location'):
'No location';detail.textContent=d.ready?`Fuel ${fmt(d.fuel_percent,'%')} · Range ${fmt(
d.range_km,' km')} · ${d.parked_since?'Parked since '+d.parked_since:'Last '+(
d.observed_at||'—')}`:'Waiting for GPS';const lat=Number(d.latitude),lon=Number(d.longitude);
if(!Number.isFinite(lat)||!Number.isFinite(lon)){status.textContent=
'Exact GPS is not available in the latest snapshot.';return}parkCoord=[lon,lat];
if(!parkMap){parkMap=makeMap('park-map',parkCoord,15);parkMap.once('load',()=>{
parkMarker=new maplibregl.Marker({color:'#47d18c'}).setLngLat(parkCoord)
.setPopup(new maplibregl.Popup().setText(d.label||'Lexus')).addTo(parkMap);status.textContent=
`${d.label||'Lexus'} · use +/−, wheel, or pinch to zoom`;});}else if(parkMarker){
parkMarker.setLngLat(parkCoord)}status.textContent=`${d.label||'Lexus'} · street map ready`;
}catch(e){main.textContent='Unavailable';status.textContent=`Parking map error: ${e.message}`}}
async function loadFuel(){try{const d=await getJSON('/api/fuel/analytics');const econ=
d.average_l_per_100km;document.querySelector('#fuel-main').textContent=econ===null||
econ===undefined?'Need 2 fill-ups':`${econ} L/100 km`;document.querySelector('#fuel-detail')
.textContent=`30d: $${Number(d.spend_30d||0).toFixed(2)} · ${d.liters_30d||0} L · ${
d.average_cost_per_km===null?'—':'$'+d.average_cost_per_km+'/km'}`}catch(_e){}}
async function loadWeekly(){try{const d=await getJSON('/api/weekly');document.querySelector(
'#week-main').textContent=`${d.distance_km||0} km`;document.querySelector('#week-detail')
.textContent=`${d.trip_count||0} trips · avg ${d.average_trip_km||0} km · longest ${
d.longest_trip_km||0} km`}catch(_e){}}
async function loadLocations(){const d=await getJSON('/api/locations');document.querySelector(
'#locations').innerHTML=d.length?d.map(x=>`<div class="row"><span>${x.name}</span><span
class="muted">${x.radius_m} m${x.is_private?' · private':''}</span></div>`).join(''):
'<div class="muted">No named locations yet.</div>'}
async function loadMaintenance(){const d=await getJSON('/api/maintenance?limit=6');
document.querySelector('#maintenance').innerHTML=d.length?d.map(x=>`<div class="row"><span>${
x.kind}</span><span class="muted">${x.odometer_km===null?'—':x.odometer_km+' km'}</span>
</div>`).join(''):'<div class="muted">No maintenance records yet.</div>'}
async function loadTimeline(){
 const d=await getJSON('/api/timeline?limit=10');
 document.querySelector('#timeline').innerHTML=d.length?d.map(x=>
 `<div class="timeline-item"><div>${x.text}</div><div class="muted">${x.at}</div></div>`
 ).join(''):'<div class="muted">No events yet.</div>'
}
async function loadTrips(){const d=await getJSON('/api/trips?limit=10');const root=
document.querySelector('#trip-list');root.innerHTML='';d.forEach(t=>{const b=document.createElement(
'button');b.type='button';b.textContent=`${t.start_label||'Start'} → ${t.end_label||'End'} · ${
t.distance_km} km`;b.disabled=!t.has_route;b.dataset.tripId=t.id;b.onclick=()=>showTrip(t.id,b);
root.appendChild(b)});if(!d.length)root.innerHTML='<span class="muted">No trips yet.</span>'}
function stopReplay(){if(replayFrame)cancelAnimationFrame(replayFrame);replayFrame=null;
replayStartedAt=null;document.querySelector('#replay-play').textContent='Play replay'}
function replayMeta(f){if(!replayPoints.length)return;const i=Math.min(replayPoints.length-1,
Math.round(f*(replayPoints.length-1)));const p=replayPoints[i];document.querySelector(
'#replay-meta').innerHTML=`<span>${p.observed_at||'—'}</span><span>Speed ${fmt(p.speed_kph,
' km/h')}</span><span>Fuel ${fmt(p.fuel_percent,'%')}</span><span>Odo ${fmt(p.odometer_km,
' km')}</span>`}
function setReplayFraction(f){if(!routeCoords.length)return;const c=coordAtFraction(routeCoords,f);
if(!replayMarker)replayMarker=new maplibregl.Marker({color:'#8ecbff'}).setLngLat(c)
.addTo(tripMap);else replayMarker.setLngLat(c);document.querySelector('#replay-slider').value=
String(Math.round(f*1000));replayMeta(f)}
function playReplay(){const button=document.querySelector('#replay-play');if(replayFrame){
stopReplay();return}const slider=document.querySelector('#replay-slider');replayStartValue=
Number(slider.value)/1000;const speed=Number(document.querySelector('#replay-speed').value)||1;
const duration=12000/speed;replayStartedAt=performance.now();button.textContent='Pause';
const tick=now=>{const elapsed=now-replayStartedAt;const f=Math.min(1,replayStartValue+
elapsed/duration*(1-replayStartValue));setReplayFraction(f);if(f<1)replayFrame=
requestAnimationFrame(tick);else{replayFrame=null;replayStartedAt=null;
button.textContent='Replay again';slider.value='0'}};replayFrame=requestAnimationFrame(tick)}
async function showTrip(id,button){stopReplay();document.querySelectorAll('#trip-list button')
.forEach(b=>b.classList.toggle('active',b===button));const status=document.querySelector(
'#trip-status');status.textContent='Loading trip and road geometry…';try{const [route,replay]=
await Promise.all([getJSON(`/api/trips/${id}/route`),getJSON(`/api/trips/${id}/replay`)]);
const stored=(route.points||[]).map(p=>[Number(p.longitude),Number(p.latitude)]).filter(isCoord);
if(stored.length<2)throw new Error('This trip does not have two usable GPS points.');routeCoords=
await roadRoute(stored);replayPoints=(replay.points||[]).filter(p=>Number.isFinite(Number(
p.latitude))&&Number.isFinite(Number(p.longitude)));if(!replayPoints.length)replayPoints=
(route.points||[]);const draw=()=>{addLine(tripMap,'trip-route',routeCoords,'#3198e6',5);
if(startMarker)startMarker.remove();
if(endMarker)endMarker.remove();
startMarker=new maplibregl.Marker({color:'#47d18c'}).setLngLat(stored[0])
.setPopup(new maplibregl.Popup().setText(route.start_label||'Trip start')).addTo(tripMap);
endMarker=new maplibregl.Marker({color:'#ff5f5f'}).setLngLat(stored.at(-1))
.setPopup(new maplibregl.Popup().setText(route.end_label||'Trip end')).addTo(tripMap);
fitMap(tripMap,routeCoords,16);setReplayFraction(0)};if(!tripMap){tripMap=
makeMap('trip-map',stored[0],13);tripMap.once('load',draw)}else if(mapIsReady(tripMap))draw();
else tripMap.once('load',draw);
const slider=document.querySelector('#replay-slider');
slider.disabled=false;slider.value='0';
slider.oninput=e=>{stopReplay();setReplayFraction(Number(e.target.value)/1000)};
const play=document.querySelector('#replay-play');
play.disabled=false;play.textContent='Play replay';
status.textContent=`${route.start_label||'Start'} → ${route.end_label||'End'} · ${
route.distance_km} km · ${stored.length} Lexus GPS sample${stored.length===1?'':'s'}`;
}catch(e){status.textContent=`Trip replay error: ${e.message}`}}
document.querySelector('#replay-play').onclick=playReplay;
document.querySelector('#center-car').onclick=()=>{if(parkMap&&parkCoord)parkMap.easeTo({
center:parkCoord,zoom:15,duration:500})};
document.querySelector('#location-form').onsubmit=async e=>{e.preventDefault();const payload={
name:document.querySelector('#location-name').value,radius_m:Number(document.querySelector(
'#location-radius').value),is_private:document.querySelector('#location-private').checked};
const r=await fetch('/api/locations/current',{method:'POST',headers:{'Content-Type':
'application/json'},body:JSON.stringify(payload)});if(!r.ok){alert(await r.text());return}
document.querySelector('#location-name').value='';await loadLocations();await loadWhere()};
document.querySelector('#maintenance-form').onsubmit=async e=>{e.preventDefault();const cost=
document.querySelector('#maintenance-cost').value;const due=document.querySelector(
'#maintenance-next').value;const payload={kind:document.querySelector('#maintenance-kind').value,
cost:cost?Number(cost):null,next_due_km:due?Number(due):null};const r=await fetch(
'/api/maintenance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(
payload)});if(!r.ok){alert(await r.text());return}e.target.reset();await loadMaintenance();
await loadTimeline()};
Promise.allSettled([loadWhere(),loadFuel(),loadWeekly(),loadLocations(),loadMaintenance(),
loadTimeline(),loadTrips()]);
</script>
</body></html>'''
    return HTMLResponse(html.replace("__ROUTER_BASE__", router_base))
