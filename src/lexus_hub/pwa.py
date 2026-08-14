from __future__ import annotations

"""Installable mobile PWA and health-score API for the private Lexus hub."""

import base64

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .config import get_settings
from .db import init_db, session_scope
from .health import vehicle_health_score

router = APIRouter(tags=["mobile app"])

_ICON_192 = "iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAIAAADdvvtQAAADTklEQVR42u3bu01rQRRAUXvkiIQIIlJERBc0QD+E7ocG6IIIkRJRBSGWbQyMz8ydz9rRk4XEfb5LZ44/rC8ur1ZSbslTIIAEkAASQBJAAkgACSAJIAEkgASQBJCC27RwEduXT3cir6eH62UvYL3U94GgGQNTbUDcDCapEiBuRpVUA9CveraPd252JpHnt2UNlQV0gg40NTGVY1QQ0FE93CwlqZChIoDQmYdRPKBDPeg0xSjWUKJn7A6f/9hXxIkehpo4wvauCZ32j7OQsyzRM+0oCplDiR6GWlqi6elwJVoSkA+5uvd03h1Mgb/b+JnwIEuFrkmTHGT5gHbZ0tO7oewhlM7Xo5mXoRQLWbMdZP4qQ9UB2X5sQiaQlptAUj4g55dTzASSI0wAaTpAFiBrkAmkyDaegqLtfQ15vLENUCU6uw+OxAigSnRGZWQHqq0n4ycBkpfxKjBUBhhCAAmgPsfPGEMIIAEkgNRpHb+R+PH+evTxm9t799UE6q+8d5Z7fz8aIAHU7RAa4OMwgARQn0NojE/jfZ2jlKETbzH7PpAyGflGouZ6lW4HEkACSABJAAkgASSAJIAEkAASQAJIAkgACSABJAEkgASQAJIAEkACSABJAAkgASSABJAEkAASQAJIAkgACSABJAEkgASQAJIAEkACSABJAAkgASSABJAEkAASQAJIAkgACSABJAEkgNRWm/H+Sx/vr31d8M3tvQkkR5gEkOxA/14dult6TCAJIAEkO1DkMiQTSAAJIAkgASSABJAEkAASQAJIAkgAqUNATw/X3/9+fvP0DdPu3dy9yyaQHGECSABZgyxAJpAcYeoekFPM+WUCqZkjzBAaY/xUBZQx69Q6pqx7mkJ+nyE04fYTvAMxNNvhFQBojy1Dneo5ZyE5dwJZhuZcfUq9jDeE5jm84l7GO8imPLwiJxBDc+pZrVbri8urqOvbvnzuP/J457a1eWxFLa+RO9DhNRlFY+spsEQzNJOe4CPsxFnmOGvk1Vb42y5FAGE0A53igH4yRFJNN0X1FAf0KyOYyqEpTaceoL8YUhFe5T9oqgSIpMHcLAaIpDHcLA8Ipn7RNAdI/eavMgSQABJAAkgCSAAJIAEkASSABJAAko70Bc1yGpSP0RipAAAAAElFTkSuQmCC"
_ICON_512 = "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"


def _icon_response(encoded: str) -> Response:
    return Response(
        content=base64.b64decode(encoded),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/api/health-score")
def api_health_score() -> dict[str, object]:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        return vehicle_health_score(session, settings)


@router.get("/pwa/icon-192.png", include_in_schema=False)
def pwa_icon_192() -> Response:
    return _icon_response(_ICON_192)


@router.get("/pwa/icon-512.png", include_in_schema=False)
def pwa_icon_512() -> Response:
    return _icon_response(_ICON_512)


@router.get("/manifest.webmanifest", include_in_schema=False)
def pwa_manifest() -> JSONResponse:
    return JSONResponse(
        {
            "name": "Lexus Personal Hub",
            "short_name": "Lexus Hub",
            "description": "Private read-only Lexus telemetry, trips, maps, and vehicle readiness.",
            "id": "/app",
            "start_url": "/app",
            "scope": "/",
            "display": "standalone",
            "background_color": "#090d12",
            "theme_color": "#111820",
            "icons": [
                {
                    "src": "/pwa/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
                {
                    "src": "/pwa/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
            ],
            "shortcuts": [
                {"name": "Garage", "url": "/garage"},
                {"name": "Vehicle status", "url": "/"},
            ],
        },
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/sw.js", include_in_schema=False)
def pwa_service_worker() -> Response:
    script = r"""
const CACHE = 'lexus-hub-shell-v1';
const SHELL = ['/app', '/manifest.webmanifest', '/pwa/icon-192.png', '/pwa/icon-512.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith('lexus-hub-shell-') && key !== CACHE)
      .map(key => caches.delete(key))
  )));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(event.request));
    return;
  }
  if (!SHELL.includes(url.pathname)) return;
  event.respondWith(
    fetch(event.request)
      .then(response => {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
""".strip()
    return Response(
        content=script,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
def mobile_app() -> HTMLResponse:
    return HTMLResponse(
        r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#111820">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Lexus Hub">
<title>Lexus Hub</title>
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/pwa/icon-192.png">
<style>
:root{--bg:#090d12;--panel:#121a23;--panel2:#151e28;--line:#283442;--text:#f6f7f9;
--muted:#8ea0b2;--accent:#8ecbff;--good:#47d18c;--warn:#ffcc66;--bad:#ff6b6b}
*{box-sizing:border-box}html{background:var(--bg)}body{margin:0;background:radial-gradient(circle at top right,
#172331 0,#090d12 38%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,
Segoe UI,sans-serif;min-height:100vh;padding-bottom:env(safe-area-inset-bottom)}main{max-width:760px;margin:auto;
padding:max(22px,env(safe-area-inset-top)) 16px 38px}header{display:flex;align-items:center;
justify-content:space-between;gap:12px;margin-bottom:16px}.brand{display:flex;gap:11px;align-items:center}.icon{
width:44px;height:44px;border-radius:13px;border:1px solid #38516a;background:#121c26;object-fit:cover}
.kicker{font-size:.7rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase}h1{margin:2px 0 0;
font-size:1.35rem}.install{border:1px solid #38516a;background:#162535;color:#a9d8ff;border-radius:10px;
padding:8px 10px;font:inherit;cursor:pointer}.install.hidden{display:none}.hero,.card{background:linear-gradient(180deg,
var(--panel2),var(--panel));border:1px solid var(--line);border-radius:20px;box-shadow:0 16px 45px rgba(0,0,0,.17)}
.hero{padding:20px;display:grid;grid-template-columns:142px 1fr;gap:20px;align-items:center}.ring{--score:0;
width:132px;height:132px;border-radius:50%;background:conic-gradient(var(--good) calc(var(--score)*1%),#26323e 0);
display:grid;place-items:center;position:relative}.ring:after{content:'';position:absolute;inset:10px;border-radius:50%;
background:#111820}.score{position:relative;z-index:1;text-align:center}.score strong{display:block;font-size:2.35rem;
line-height:1}.score span{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.grade{font-size:1.45rem;font-weight:780}.sub{color:var(--muted);font-size:.82rem;line-height:1.45;margin-top:6px}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}.metric{padding:14px;background:#0d141b;
border:1px solid var(--line);border-radius:15px}.metric span{display:block;color:var(--muted);font-size:.68rem;
text-transform:uppercase;letter-spacing:.07em}.metric strong{display:block;margin-top:6px;font-size:1.1rem}.grid{
display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}.card{padding:17px}.card h2{font-size:.9rem;
margin:0 0 12px}.check{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-bottom:1px solid rgba(142,160,178,.11)}
.check:last-child{border-bottom:0}.dot{width:9px;height:9px;border-radius:50%;margin-top:5px;flex:0 0 auto}.dot.ok{background:var(--good)}
.dot.warn{background:var(--warn)}.dot.alert{background:var(--bad)}.dot.unknown{background:var(--muted)}.check-name{
font-size:.84rem;font-weight:680}.check-detail{font-size:.74rem;color:var(--muted);margin-top:2px;line-height:1.4}
.where-main{font-size:1.08rem;font-weight:720}.trip{padding:9px 0;border-bottom:1px solid rgba(142,160,178,.11)}
.trip:last-child{border-bottom:0}.trip-route{font-size:.82rem;font-weight:650}.trip-meta{font-size:.72rem;color:var(--muted);margin-top:3px}
.nav{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}.nav a{color:var(--text);text-decoration:none;
text-align:center;padding:13px 8px;background:#101821;border:1px solid var(--line);border-radius:14px;font-size:.8rem}
.statusline{margin-top:12px;color:var(--muted);font-size:.7rem;text-align:center}.offline{color:var(--warn)}
@media(max-width:560px){.hero{grid-template-columns:112px 1fr;gap:14px}.ring{width:104px;height:104px}.ring:after{inset:8px}
.score strong{font-size:1.9rem}.grade{font-size:1.2rem}.grid{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(3,1fr)}
.metric{padding:11px}.metric strong{font-size:.96rem}.nav{position:sticky;bottom:8px;background:rgba(9,13,18,.88);backdrop-filter:blur(12px);
padding:8px;border-radius:18px;border:1px solid rgba(40,52,66,.75)}}
</style>
</head>
<body><main>
<header><div class="brand"><img class="icon" src="/pwa/icon-192.png" alt=""><div><div class="kicker">Private vehicle hub</div>
<h1 id="vehicle-name">Lexus Hub</h1></div></div><button id="install" class="install hidden">Install</button></header>
<section class="hero"><div id="ring" class="ring"><div class="score"><strong id="score">—</strong><span>Health</span></div></div>
<div><div id="grade" class="grade">Loading…</div><div id="health-sub" class="sub">Checking the latest saved vehicle telemetry.</div></div></section>
<section class="metrics"><div class="metric"><span>Fuel</span><strong id="fuel">—</strong></div><div class="metric"><span>Range</span><strong id="range">—</strong></div>
<div class="metric"><span>Odometer</span><strong id="odo">—</strong></div></section>
<section class="grid"><article class="card"><h2>Readiness checks</h2><div id="checks"><div class="sub">Loading…</div></div></article>
<article class="card"><h2>Where's my Lexus?</h2><div id="where-main" class="where-main">Loading…</div><div id="where-detail" class="sub"></div></article>
<article class="card" style="grid-column:1/-1"><h2>Recent trips</h2><div id="trips"><div class="sub">Loading…</div></div></article></section>
<nav class="nav"><a href="/">Vehicle</a><a href="/garage">Garage</a><a href="/docs">API</a></nav>
<div id="statusline" class="statusline">Live data is never cached by the app.</div>
</main>
<script>
const $=s=>document.querySelector(s);
const fmt=(v,s='')=>v===null||v===undefined?'—':`${Number(v).toLocaleString()}${s}`;
const getJSON=async url=>{const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw new Error(await r.text());return r.json()};
function node(tag,cls,text){const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el}
async function load(){try{const [health,status,where,trips]=await Promise.all([
getJSON('/api/health-score'),getJSON('/api/status'),getJSON('/api/where'),getJSON('/api/trips?limit=4')]);
const vehicle=status.vehicle||{};$('#vehicle-name').textContent=vehicle.display_name||'Lexus Hub';$('#fuel').textContent=fmt(status.fuel_percent,'%');
$('#range').textContent=fmt(status.range_km,' km');$('#odo').textContent=fmt(status.odometer_km,' km');
if(health.ready){$('#score').textContent=health.score;$('#ring').style.setProperty('--score',health.score);$('#grade').textContent=health.grade;
$('#health-sub').textContent=health.attention_count?`${health.attention_count} item${health.attention_count===1?'':'s'} need attention. ${health.disclaimer}`:health.disclaimer;
const root=$('#checks');root.replaceChildren();(health.checks||[]).forEach(c=>{const row=node('div','check');row.appendChild(node('span',`dot ${c.state}`));
const body=node('div');body.appendChild(node('div','check-name',c.name));body.appendChild(node('div','check-detail',c.detail));row.appendChild(body);root.appendChild(row)})}
else{$('#grade').textContent='Waiting for telemetry';$('#health-sub').textContent='Poll the Lexus to calculate a score.'}
if(where.ready){$('#where-main').textContent=where.label||'Unknown location';$('#where-detail').textContent=`${where.parked_since?'Parked since '+where.parked_since:'Last saved '+(where.observed_at||'—')} · Fuel ${fmt(where.fuel_percent,'%')} · Range ${fmt(where.range_km,' km')}`}
else{$('#where-main').textContent='No saved location';$('#where-detail').textContent='Waiting for location telemetry.'}
const tripsRoot=$('#trips');tripsRoot.replaceChildren();if(!trips.length)tripsRoot.appendChild(node('div','sub','No trips detected yet.'));else trips.forEach(t=>{
const row=node('div','trip');row.appendChild(node('div','trip-route',`${t.start_label||'Start'} → ${t.end_label||'End'}`));
row.appendChild(node('div','trip-meta',`${t.distance_km} km · ${t.started_at||'—'}`));tripsRoot.appendChild(row)})}
catch(err){$('#grade').textContent='Unavailable';$('#health-sub').textContent='Could not load live vehicle data.';$('#statusline').textContent='Connection unavailable';$('#statusline').classList.add('offline')}}
load();setInterval(load,60000);
if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}))}
let installPrompt=null;window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;$('#install').classList.remove('hidden')});
$('#install').addEventListener('click',async()=>{if(installPrompt){installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;$('#install').classList.add('hidden')}
else{alert('On iPhone/iPad: open this page in Safari, tap Share, then Add to Home Screen.') }});
window.addEventListener('appinstalled',()=>$('#install').classList.add('hidden'));
</script>
</body></html>""",
        headers={"Cache-Control": "no-cache"},
    )
