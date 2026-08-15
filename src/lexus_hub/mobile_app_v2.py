from __future__ import annotations

"""Mobile-first Lexus Hub shell inspired by the information hierarchy of the OEM app."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

router = APIRouter(tags=["mobile app v2"])


@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
def mobile_app_v2() -> HTMLResponse:
    return HTMLResponse(
        r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#090d12">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Lexus Hub">
<title>Lexus Hub</title>
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/pwa/icon-192.png">
<style>
:root{--bg:#080c11;--panel:#111820;--panel2:#151e28;--panel3:#0d141b;--line:#283442;
--text:#f7f8fa;--muted:#8fa1b3;--muted2:#647586;--accent:#71bfff;--accent2:#a7dcff;
--good:#49d690;--warn:#ffc85c;--bad:#ff6767;--shadow:0 18px 50px rgba(0,0,0,.24)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html{background:var(--bg);scroll-behavior:smooth}
body{margin:0;background:radial-gradient(circle at 86% -10%,#1b2b3b 0,#0b1118 24%,var(--bg) 48%);
color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
min-height:100vh;padding-bottom:calc(94px + env(safe-area-inset-bottom))}
button,a{font:inherit}button{color:inherit}.shell{max-width:760px;margin:auto;padding:max(18px,env(safe-area-inset-top)) 16px 28px}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:2px 0 18px}
.vehicle-title{min-width:0}.eyebrow{font-size:.64rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.vehicle-name{font-size:1.65rem;font-weight:820;line-height:1.05;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sync-line{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:.72rem;margin-top:7px}.sync-dot{width:8px;height:8px;border-radius:50%;background:var(--muted2)}
.sync-dot.good{background:var(--good);box-shadow:0 0 12px rgba(73,214,144,.45)}.sync-dot.warn{background:var(--warn)}
.top-actions{display:flex;gap:8px;align-items:center}.round-button{width:42px;height:42px;border-radius:14px;border:1px solid #35506a;background:rgba(18,31,43,.92);
display:grid;place-items:center;cursor:pointer;font-size:1.05rem;box-shadow:0 8px 24px rgba(0,0,0,.2)}
.round-button:disabled{opacity:.55;cursor:wait}.connection-pill{border:1px solid var(--line);background:#0e161f;color:var(--muted);padding:8px 10px;border-radius:999px;font-size:.66rem;white-space:nowrap}
.range-card{background:linear-gradient(145deg,#151e28,#0f171f 72%);border:1px solid var(--line);border-radius:24px;padding:20px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.range-card:after{content:"";position:absolute;width:180px;height:180px;border-radius:50%;right:-70px;top:-95px;background:radial-gradient(circle,rgba(113,191,255,.16),transparent 68%);pointer-events:none}
.range-top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.range-value{font-size:2.35rem;font-weight:850;letter-spacing:-.04em;line-height:1}.range-value small{font-size:.9rem;font-weight:700;letter-spacing:0}
.range-label{color:var(--muted);font-size:.76rem;margin-top:7px}.fuel-badge{text-align:right}.fuel-badge strong{font-size:1.1rem}.fuel-badge span{display:block;color:var(--muted);font-size:.65rem;margin-top:3px}
.range-track{height:9px;border-radius:999px;background:#26323e;margin-top:20px;overflow:hidden}.range-fill{height:100%;width:0;border-radius:inherit;background:linear-gradient(90deg,#438fff,#84d1ff);transition:width .4s ease}
.range-foot{display:flex;justify-content:space-between;gap:12px;margin-top:10px;color:var(--muted);font-size:.68rem}
.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;background:#0d141b;border:1px solid var(--line);border-radius:17px;padding:5px;margin:14px 0}
.tab-button{border:0;background:transparent;color:var(--muted);padding:10px 5px;border-radius:12px;font-weight:720;font-size:.78rem;cursor:pointer}.tab-button.active{background:#f4f6f8;color:#111820;box-shadow:0 5px 18px rgba(0,0,0,.22)}
.view{display:none}.view.active{display:block}.stack{display:grid;gap:12px}.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:21px;padding:17px;box-shadow:0 12px 35px rgba(0,0,0,.14)}
.card-title{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:13px}.card-title h2{font-size:.9rem;margin:0}.card-title .hint{color:var(--muted);font-size:.65rem}
.health-row{display:grid;grid-template-columns:84px 1fr;gap:14px;align-items:center}.health-ring{--score:0;width:80px;height:80px;border-radius:50%;background:conic-gradient(var(--good) calc(var(--score)*1%),#273442 0);display:grid;place-items:center;position:relative}
.health-ring:after{content:"";position:absolute;inset:7px;border-radius:50%;background:#111820}.health-score{position:relative;z-index:1;text-align:center}.health-score strong{display:block;font-size:1.45rem;line-height:1}.health-score span{font-size:.55rem;color:var(--muted)}
.health-grade{font-size:1.25rem;font-weight:820}.health-detail{color:var(--muted);font-size:.72rem;line-height:1.45;margin-top:4px}
.quick-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}.quick-card{background:#0d141b;border:1px solid var(--line);border-radius:16px;padding:13px;min-width:0}.quick-icon{font-size:1rem}.quick-label{color:var(--muted);font-size:.62rem;text-transform:uppercase;letter-spacing:.06em;margin-top:7px}.quick-value{font-size:.85rem;font-weight:760;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.quick-value.good{color:var(--good)}.quick-value.warn{color:var(--warn)}.quick-value.bad{color:var(--bad)}
.location-main{font-size:1.1rem;font-weight:780;line-height:1.25}.location-sub{color:var(--muted);font-size:.72rem;line-height:1.45;margin-top:5px}.inline-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.small-button,.small-link{border:1px solid #38516a;background:#162535;color:#a9d8ff;border-radius:10px;padding:8px 10px;text-decoration:none;font-size:.72rem;cursor:pointer}
.last-trip{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center}.trip-route{font-size:.84rem;font-weight:760;line-height:1.35}.trip-meta{color:var(--muted);font-size:.68rem;margin-top:4px}.trip-distance{font-size:1.15rem;font-weight:820;color:var(--accent2);white-space:nowrap}
.vehicle-stage{position:relative;height:300px;border-radius:21px;background:radial-gradient(circle at center,#16222e,#0b1219 62%);border:1px solid #263542;overflow:hidden}.car{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:118px;height:218px;border:2px solid #65798d;border-radius:38px 38px 32px 32px;background:linear-gradient(90deg,#16212b,#263747 48%,#16212b);box-shadow:0 0 0 8px rgba(255,255,255,.018),0 18px 40px rgba(0,0,0,.32)}
.car:before{content:"";position:absolute;left:18px;right:18px;top:38px;height:52px;border-radius:18px;background:linear-gradient(180deg,#1a2835,#071018);border:1px solid #3e5264}.car:after{content:"";position:absolute;left:19px;right:19px;bottom:34px;height:47px;border-radius:16px;background:#0e1821;border:1px solid #35495a}
.car-center{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font-size:.62rem;color:var(--muted);z-index:2;text-align:center;line-height:1.35}.car-center strong{display:block;color:var(--text);font-size:.75rem;margin-bottom:2px}
.tire-tag{position:absolute;min-width:82px;text-align:center}.tire-tag strong{display:block;font-size:1rem}.tire-tag span{display:block;color:var(--muted);font-size:.6rem;margin-top:2px}.tire-fl{left:13px;top:48px}.tire-fr{right:13px;top:48px}.tire-rl{left:13px;bottom:48px}.tire-rr{right:13px;bottom:48px}
.status-cards{display:grid;gap:9px}.status-card{display:grid;grid-template-columns:44px 1fr auto;gap:11px;align-items:center;padding:13px;background:#0d141b;border:1px solid var(--line);border-radius:16px}.status-icon{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;background:#111c26;font-size:1.05rem}.status-name{font-size:.86rem;font-weight:760}.status-value{font-size:.72rem;color:var(--muted);margin-top:2px}.state-dot{width:10px;height:10px;border-radius:50%;background:var(--muted)}.state-dot.good{background:var(--good)}.state-dot.warn{background:var(--warn)}.state-dot.bad{background:var(--bad)}
.check-list{display:grid;gap:0}.check{display:flex;gap:10px;padding:10px 0;border-bottom:1px solid rgba(142,160,178,.11)}.check:last-child{border-bottom:0}.check-dot{width:9px;height:9px;border-radius:50%;margin-top:4px;flex:0 0 auto;background:var(--muted)}.check-dot.ok{background:var(--good)}.check-dot.warn{background:var(--warn)}.check-dot.alert{background:var(--bad)}.check-name{font-size:.78rem;font-weight:730}.check-detail{font-size:.68rem;color:var(--muted);line-height:1.4;margin-top:2px}
.trip-list{display:grid;gap:10px}.trip-card{background:linear-gradient(180deg,#131c25,#0d151d);border:1px solid var(--line);border-radius:18px;padding:14px}.trip-card-head{display:flex;justify-content:space-between;gap:12px}.trip-card-route{font-size:.84rem;font-weight:780;line-height:1.35}.trip-card-distance{font-size:.9rem;font-weight:820;color:var(--accent2);white-space:nowrap}.trip-card-time{font-size:.65rem;color:var(--muted);margin-top:4px}.trip-stats-v2{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:11px}.trip-stat-v2{background:#091119;border:1px solid #243341;border-radius:11px;padding:8px}.trip-stat-v2 span{display:block;color:var(--muted);font-size:.56rem;text-transform:uppercase;letter-spacing:.05em}.trip-stat-v2 strong{display:block;font-size:.72rem;margin-top:3px}.trip-note{color:var(--muted);font-size:.62rem;line-height:1.4;margin-top:10px}
.connection-card{display:grid;gap:8px}.connection-mode{font-size:.92rem;font-weight:760}.connection-origin{font-size:.66rem;color:var(--muted);overflow-wrap:anywhere}
.loading{color:var(--muted);font-size:.75rem}.empty{color:var(--muted);font-size:.75rem;padding:6px 0}.error-banner{display:none;background:#2c1b1b;border:1px solid #663737;color:#ffc0c0;border-radius:14px;padding:11px 12px;font-size:.72rem;line-height:1.45;margin-bottom:12px}.error-banner.show{display:block}
.bottom-nav{position:fixed;left:50%;bottom:max(8px,env(safe-area-inset-bottom));transform:translateX(-50%);width:min(730px,calc(100% - 20px));height:70px;background:rgba(10,15,21,.93);backdrop-filter:blur(18px);border:1px solid rgba(51,68,84,.9);border-radius:22px;display:grid;grid-template-columns:repeat(4,1fr);z-index:20;box-shadow:0 18px 46px rgba(0,0,0,.42);padding:5px}
.bottom-item{border:0;background:transparent;color:var(--muted);text-decoration:none;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;border-radius:16px;font-size:.61rem;cursor:pointer}.bottom-item .nav-icon{font-size:1.1rem}.bottom-item.active{background:#162330;color:#fff}.bottom-item.active .nav-icon{color:var(--accent2)}
@media(min-width:600px){.stack.two{grid-template-columns:1fr 1fr}.vehicle-stage{height:330px}.trip-stats-v2{grid-template-columns:repeat(6,1fr)}}
@media(max-width:390px){.shell{padding-left:12px;padding-right:12px}.connection-pill{display:none}.range-value{font-size:2rem}.quick-grid{grid-template-columns:1fr 1fr}.quick-grid .quick-card:last-child{grid-column:1/-1}.vehicle-stage{height:278px}.tire-tag{min-width:66px}.trip-stats-v2{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<main class="shell">
<div id="error-banner" class="error-banner"></div>
<header class="topbar">
  <div class="vehicle-title">
    <div class="eyebrow">Private vehicle hub</div>
    <div id="vehicle-name" class="vehicle-name">Lexus Hub</div>
    <div class="sync-line"><span id="sync-dot" class="sync-dot"></span><span id="last-sync">Loading latest telemetry…</span></div>
  </div>
  <div class="top-actions">
    <div id="connection-pill" class="connection-pill">Connecting…</div>
    <button id="vehicle-refresh-button" class="round-button" type="button" aria-label="Refresh vehicle telemetry" title="Refresh vehicle telemetry">↻</button>
  </div>
</header>

<section class="range-card">
  <div class="range-top">
    <div><div id="range-main" class="range-value">— <small>km</small></div><div class="range-label">Distance to empty</div></div>
    <div class="fuel-badge"><strong id="fuel-main">—</strong><span>Fuel level</span></div>
  </div>
  <div class="range-track"><div id="range-fill" class="range-fill"></div></div>
  <div class="range-foot"><span id="odometer-main">Odometer —</span><span id="speed-main">Parked</span></div>
</section>

<nav class="tabs" aria-label="Vehicle sections">
  <button class="tab-button active" data-tab="overview" type="button">Overview</button>
  <button class="tab-button" data-tab="status" type="button">Status</button>
  <button class="tab-button" data-tab="trips" type="button">Trips</button>
</nav>

<section id="view-overview" class="view active">
  <div class="stack">
    <article class="card">
      <div class="card-title"><h2>Vehicle health</h2><span id="health-updated" class="hint">Live</span></div>
      <div class="health-row">
        <div id="health-ring" class="health-ring"><div class="health-score"><strong id="health-score">—</strong><span>score</span></div></div>
        <div><div id="health-grade" class="health-grade">Loading…</div><div id="health-detail" class="health-detail">Checking saved Lexus telemetry.</div></div>
      </div>
    </article>

    <div class="quick-grid">
      <article class="quick-card"><div class="quick-icon">🔒</div><div class="quick-label">Doors</div><div id="quick-locks" class="quick-value">—</div></article>
      <article class="quick-card"><div class="quick-icon">▭</div><div class="quick-label">Windows</div><div id="quick-windows" class="quick-value">—</div></article>
      <article class="quick-card"><div class="quick-icon">◉</div><div class="quick-label">Tires</div><div id="quick-tires" class="quick-value">—</div></article>
    </div>

    <div class="stack two">
      <article class="card">
        <div class="card-title"><h2>Where's my Lexus?</h2><span class="hint">Parked location</span></div>
        <div id="where-main" class="location-main">Loading…</div><div id="where-detail" class="location-sub"></div>
        <div class="inline-actions"><a class="small-link" href="/garage">Open parking map</a></div>
      </article>
      <article class="card">
        <div class="card-title"><h2>Latest trip</h2><button class="small-button" type="button" data-go-tab="trips">All trips</button></div>
        <div id="latest-trip" class="loading">Loading…</div>
      </article>
    </div>

    <article id="connection-card" class="card connection-card">
      <div class="card-title"><h2>Connection</h2><span class="hint">Private access</span></div>
      <div id="connection-mode" class="connection-mode">Checking route…</div>
      <div id="connection-origin" class="connection-origin"></div>
      <div id="connection-actions" class="inline-actions"></div>
    </article>
  </div>
</section>

<section id="view-status" class="view">
  <div class="stack">
    <article class="card">
      <div class="card-title"><h2>Tire pressure</h2><span id="tire-updated" class="hint">Latest reported</span></div>
      <div class="vehicle-stage">
        <div class="tire-tag tire-fl"><strong id="tire-fl">—</strong><span>Front driver</span></div>
        <div class="tire-tag tire-fr"><strong id="tire-fr">—</strong><span>Front passenger</span></div>
        <div class="tire-tag tire-rl"><strong id="tire-rl">—</strong><span>Rear driver</span></div>
        <div class="tire-tag tire-rr"><strong id="tire-rr">—</strong><span>Rear passenger</span></div>
        <div class="car"><div class="car-center"><strong id="car-security">Checking…</strong><span id="car-security-sub">doors · windows · locks</span></div></div>
      </div>
    </article>

    <div class="status-cards">
      <article class="status-card"><div class="status-icon">▣</div><div><div class="status-name">Doors & body</div><div id="doors-status" class="status-value">Loading…</div></div><span id="doors-dot" class="state-dot"></span></article>
      <article class="status-card"><div class="status-icon">▭</div><div><div class="status-name">Windows & moonroof</div><div id="windows-status" class="status-value">Loading…</div></div><span id="windows-dot" class="state-dot"></span></article>
      <article class="status-card"><div class="status-icon">🔒</div><div><div class="status-name">Locks</div><div id="locks-status" class="status-value">Loading…</div></div><span id="locks-dot" class="state-dot"></span></article>
    </div>

    <article class="card"><div class="card-title"><h2>Readiness checks</h2><span class="hint">Freshness-aware</span></div><div id="checks" class="check-list"><div class="loading">Loading…</div></div></article>
  </div>
</section>

<section id="view-trips" class="view">
  <div class="stack">
    <article class="card">
      <div class="card-title"><h2>Recent trips</h2><a class="small-link" href="/garage">Garage & replay</a></div>
      <div id="trips" class="trip-list"><div class="loading">Loading trip history…</div></div>
      <div class="trip-note">Top speed is the highest saved telemetry sample. Short speed peaks between vehicle updates may not be captured.</div>
    </article>
  </div>
</section>

<div id="statusline" class="loading" style="text-align:center;margin-top:14px">Live vehicle data is requested directly from Lexus Hub.</div>
</main>

<nav class="bottom-nav" aria-label="Primary navigation">
  <button class="bottom-item active" data-tab="overview" type="button"><span class="nav-icon">⌂</span><span>Home</span></button>
  <button class="bottom-item" data-tab="status" type="button"><span class="nav-icon">◫</span><span>Status</span></button>
  <button class="bottom-item" data-tab="trips" type="button"><span class="nav-icon">↗</span><span>Trips</span></button>
  <a class="bottom-item" href="/garage"><span class="nav-icon">▦</span><span>Garage</span></a>
</nav>

<script>
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const getJSON=async url=>{const r=await fetch(url,{cache:'no-store',headers:{Accept:'application/json'}});if(!r.ok)throw new Error(await r.text());return r.json()};
const fmt=(v,s='',digits=0)=>v===null||v===undefined||Number.isNaN(Number(v))?'—':`${Number(v).toLocaleString(undefined,{maximumFractionDigits:digits})}${s}`;
const safeText=v=>v===null||v===undefined||v===''?'—':String(v);
const record=(status,key)=>{const v=(status||{})[key];return v&&typeof v==='object'?v:{}};
const recValue=(status,key)=>record(status,key).value;
const recDisplay=(status,key)=>safeText(record(status,key).display||record(status,key).value);
const norm=v=>String(v??'').trim().toLowerCase();
const isOpen=v=>['open','on','unlocked','true','1','running'].includes(norm(v));
const isClosed=v=>['closed','off','locked','false','0'].includes(norm(v));
const ago=value=>{if(!value)return 'Unknown update time';const d=new Date(value);if(Number.isNaN(d.getTime()))return String(value);const sec=Math.max(0,(Date.now()-d.getTime())/1000);if(sec<60)return 'Updated just now';if(sec<3600)return `Updated ${Math.round(sec/60)} min ago`;if(sec<86400)return `Updated ${Math.round(sec/3600)} hr ago`;return `Updated ${Math.round(sec/86400)} d ago`};
const stateClass=(ok,warn=false)=>ok?'good':warn?'warn':'bad';

let cached={status:null,health:null,where:null,trips:[],access:null};

function setTab(name,push=true){
  const valid=['overview','status','trips'];if(!valid.includes(name))name='overview';
  $$('.view').forEach(v=>v.classList.toggle('active',v.id===`view-${name}`));
  $$('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
  if(push){const hash=name==='overview'?'#overview':`#${name}`;if(location.hash!==hash)history.replaceState(null,'',hash)}
  window.scrollTo({top:0,behavior:'smooth'});
}
$$('[data-tab]').forEach(b=>b.addEventListener('click',()=>setTab(b.dataset.tab)));
$$('[data-go-tab]').forEach(b=>b.addEventListener('click',()=>setTab(b.dataset.goTab)));
window.addEventListener('hashchange',()=>setTab(location.hash.slice(1)||'overview',false));
setTab(location.hash.slice(1)||'overview',false);

function aggregate(status,keys,goodText,badLabel){
  const values=keys.map(k=>recValue(status,k)).filter(v=>v!==undefined&&v!==null&&v!=='');
  if(!values.length)return {text:'Not reported',ok:false,unknown:true};
  const bad=values.filter(isOpen).length;
  if(bad)return {text:`${bad} ${badLabel}${bad===1?'':'s'} need attention`,ok:false,unknown:false};
  return {text:goodText,ok:true,unknown:false};
}
function tireSummary(status){
  const keys=['front_driver_tire','front_passenger_tire','rear_driver_tire','rear_passenger_tire'];
  const nums=keys.map(k=>Number(recValue(status,k))).filter(Number.isFinite);
  if(!nums.length)return {text:'Not reported',ok:false,unknown:true};
  const low=nums.some(v=>v<30);return {text:low?`${Math.min(...nums)} psi low`:`${Math.min(...nums)}–${Math.max(...nums)} psi`,ok:!low,unknown:false};
}
function paintState(el,result){el.classList.remove('good','warn','bad');el.classList.add(result.unknown?'warn':result.ok?'good':'bad')}

function renderStatus(statusPayload){
  cached.status=statusPayload;const vehicle=statusPayload.vehicle||{};const vs=statusPayload.vehicle_status||{};
  $('#vehicle-name').textContent=vehicle.display_name||'Lexus Hub';
  $('#range-main').innerHTML=`${fmt(statusPayload.range_km,'',0)} <small>km</small>`;
  $('#fuel-main').textContent=fmt(statusPayload.fuel_percent,'%',0);$('#range-fill').style.width=`${Math.max(0,Math.min(100,Number(statusPayload.fuel_percent)||0))}%`;
  $('#odometer-main').textContent=`Odometer ${fmt(statusPayload.odometer_km,' km',0)}`;
  $('#speed-main').textContent=(Number(statusPayload.speed_kph)||0)>1?`${fmt(statusPayload.speed_kph,' km/h',0)}`:'Parked';
  const sync=statusPayload.source_updated_at||statusPayload.last_poll;$('#last-sync').textContent=ago(sync);$('#sync-dot').className='sync-dot '+((Date.now()-new Date(sync).getTime())<3*3600e3?'good':'warn');

  const doors=aggregate(vs,['front_driver_door','front_passenger_door','rear_driver_door','rear_passenger_door','hood','trunk'],'All reported doors closed','opening');
  const windows=aggregate(vs,['front_driver_window','front_passenger_window','rear_driver_window','rear_passenger_window','moonroof'],'All reported windows closed','window');
  const locks=aggregate(vs,['front_driver_door_lock','front_passenger_door_lock','rear_driver_door_lock','rear_passenger_door_lock','trunk_door_lock'],'All reported locks secured','lock');
  const tires=tireSummary(vs);
  [['#quick-locks',locks],['#quick-windows',windows],['#quick-tires',tires]].forEach(([sel,r])=>{const el=$(sel);el.textContent=r.text;paintState(el,r)});
  $('#doors-status').textContent=doors.text;$('#windows-status').textContent=windows.text;$('#locks-status').textContent=locks.text;
  paintState($('#doors-dot'),doors);paintState($('#windows-dot'),windows);paintState($('#locks-dot'),locks);
  const secure=doors.ok&&windows.ok&&locks.ok;$('#car-security').textContent=secure?'Secure':(doors.unknown||windows.unknown||locks.unknown?'Partial data':'Check vehicle');$('#car-security-sub').textContent=secure?'doors · windows · locks':'review status below';

  $('#tire-fl').textContent=recDisplay(vs,'front_driver_tire');$('#tire-fr').textContent=recDisplay(vs,'front_passenger_tire');$('#tire-rl').textContent=recDisplay(vs,'rear_driver_tire');$('#tire-rr').textContent=recDisplay(vs,'rear_passenger_tire');
  const tireUpdate=record(vs,'last_tire_pressure_update').display||record(vs,'front_driver_tire').updated_at;$('#tire-updated').textContent=tireUpdate?ago(tireUpdate):'Latest reported';
}

function renderHealth(health){
  cached.health=health;if(!health.ready){$('#health-grade').textContent='Waiting for telemetry';$('#health-detail').textContent='No saved vehicle status yet.';return}
  $('#health-score').textContent=health.score;$('#health-ring').style.setProperty('--score',health.score);$('#health-grade').textContent=health.grade;
  $('#health-detail').textContent=health.attention_count?`${health.attention_count} item${health.attention_count===1?'':'s'} need attention.`:'All monitored readiness checks look good.';
  const root=$('#checks');root.replaceChildren();(health.checks||[]).forEach(c=>{const row=document.createElement('div');row.className='check';const dot=document.createElement('span');dot.className=`check-dot ${c.state}`;const body=document.createElement('div');const name=document.createElement('div');name.className='check-name';name.textContent=c.name;const detail=document.createElement('div');detail.className='check-detail';detail.textContent=c.detail;body.append(name,detail);row.append(dot,body);root.appendChild(row)});
}

function renderWhere(where){
  cached.where=where;if(!where.ready){$('#where-main').textContent='No saved location';$('#where-detail').textContent='Waiting for parked-location telemetry.';return}
  $('#where-main').textContent=where.label||'Unknown location';$('#where-detail').textContent=`${where.parked_since?'Parked since '+where.parked_since:'Last saved '+safeText(where.observed_at)} · Fuel ${fmt(where.fuel_percent,'%',0)} · Range ${fmt(where.range_km,' km',0)}`;
}
async function renderEstimatedAddress(){try{const d=await getJSON('/api/location/address');if(d.ready&&d.estimated_address&&['Unnamed location','Unknown location'].includes($('#where-main').textContent.trim()))$('#where-main').textContent=d.estimated_address}catch(_){}}

function stat(label,value){const el=document.createElement('div');el.className='trip-stat-v2';const a=document.createElement('span');a.textContent=label;const b=document.createElement('strong');b.textContent=value;el.append(a,b);return el}
async function renderTrips(trips){
  cached.trips=trips;const root=$('#trips');root.replaceChildren();
  if(!trips.length){root.innerHTML='<div class="empty">No trips detected yet.</div>';$('#latest-trip').innerHTML='<div class="empty">No completed trips yet.</div>';return}
  const detailResults=await Promise.all(trips.slice(0,6).map(async t=>{try{return await getJSON(`/api/trips/${t.id}/details`)}catch(_){return null}}));
  trips.slice(0,6).forEach((t,i)=>{const d=detailResults[i]||{};const m=d.metrics||{};const card=document.createElement('article');card.className='trip-card';const head=document.createElement('div');head.className='trip-card-head';const left=document.createElement('div');const route=document.createElement('div');route.className='trip-card-route';route.textContent=`${d.start_address||d.start_label||t.start_label||'Start'} → ${d.end_address||d.end_label||t.end_label||'End'}`;const time=document.createElement('div');time.className='trip-card-time';time.textContent=t.started_at||'—';left.append(route,time);const dist=document.createElement('div');dist.className='trip-card-distance';dist.textContent=`${t.distance_km} km`;head.append(left,dist);card.appendChild(head);const stats=document.createElement('div');stats.className='trip-stats-v2';stats.append(stat('Duration',m.duration_minutes==null?'—':`${m.duration_minutes} min`),stat('Top speed',m.top_speed_kph==null?'—':`${m.top_speed_kph} km/h`),stat('Avg speed',m.average_speed_kph==null?'—':`${m.average_speed_kph} km/h`),stat('Fuel drop',m.fuel_drop_percent==null?'—':`${m.fuel_drop_percent}%`),stat('Fuel used',m.fuel_used_liters_estimate==null?'—':`${m.fuel_used_liters_estimate} L`),stat('Samples',m.telemetry_samples==null?'—':String(m.telemetry_samples)));card.appendChild(stats);root.appendChild(card)});
  const t=trips[0],d=detailResults[0]||{};$('#latest-trip').innerHTML='';const wrap=document.createElement('div');wrap.className='last-trip';const left=document.createElement('div');const route=document.createElement('div');route.className='trip-route';route.textContent=`${d.start_address||d.start_label||t.start_label||'Start'} → ${d.end_address||d.end_label||t.end_label||'End'}`;const meta=document.createElement('div');meta.className='trip-meta';meta.textContent=t.started_at||'—';left.append(route,meta);const distance=document.createElement('div');distance.className='trip-distance';distance.textContent=`${t.distance_km} km`;wrap.append(left,distance);$('#latest-trip').appendChild(wrap);
}

async function renderAccess(){
  let access=null;try{access=await getJSON('/api/access')}catch(_){const c=window['LEXUS_CONNECTIONS']||{};access={local_url:c.local_url,remote_url:c.remote_url,mode:location.hostname===c.local_host?'local':'private_remote',current_origin:location.origin}}
  cached.access=access;const mode=access.mode==='local'?'Home LAN':'Tailscale / private';$('#connection-pill').textContent=mode;$('#connection-mode').textContent=mode;$('#connection-origin').textContent=access.current_origin||location.origin;const actions=$('#connection-actions');actions.replaceChildren();
  const add=(url,label)=>{if(!url)return;const a=document.createElement('a');a.className='small-link';a.href=url;a.textContent=label;actions.appendChild(a)};add(access.local_url,'Use Home LAN');if(access.remote_url!==access.local_url)add(access.remote_url,'Use Tailscale');
}

async function loadAll(showError=true){
  try{const [status,health,where,trips]=await Promise.all([getJSON('/api/status'),getJSON('/api/health-score'),getJSON('/api/where'),getJSON('/api/trips?limit=6')]);renderStatus(status);renderHealth(health);renderWhere(where);await Promise.all([renderEstimatedAddress(),renderTrips(trips),renderAccess()]);$('#error-banner').classList.remove('show');$('#statusline').textContent='Live vehicle data loaded.';return true}
  catch(err){if(showError){$('#error-banner').textContent='Could not load live vehicle data on this connection. Use the Connection card to switch routes, or try Refresh when connectivity returns.';$('#error-banner').classList.add('show');$('#statusline').textContent='Vehicle data unavailable on this route.'}await renderAccess();return false}
}

$('#vehicle-refresh-button').addEventListener('click',async()=>{const b=$('#vehicle-refresh-button');b.disabled=true;b.textContent='…';$('#last-sync').textContent='Requesting fresh vehicle status…';try{const r=await fetch('/api/vehicle/refresh',{method:'POST',cache:'no-store'});if(!r.ok)throw new Error(await r.text());await loadAll(false);b.textContent='✓';setTimeout(()=>{b.textContent='↻';b.disabled=false},1100)}catch(_){b.textContent='!';$('#last-sync').textContent='Refresh failed — showing last saved data';setTimeout(()=>{b.textContent='↻';b.disabled=false},1600)}});

loadAll();setInterval(()=>loadAll(false),60000);
if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}))}
</script>
</body>
</html>""",
        headers={"Cache-Control": "no-cache"},
    )


class GarageReturnLinkMiddleware(BaseHTTPMiddleware):
    """Keep the Garage page unchanged except for returning to the mobile app shell."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path != "/garage" or "text/html" not in response.headers.get(
            "content-type", ""
        ):
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode("utf-8", errors="replace")
        text = text.replace(
            '<a href="/">← Vehicle dashboard</a>',
            '<a href="/app#overview">← Lexus app</a>',
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
