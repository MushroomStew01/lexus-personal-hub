"""Small runtime hardening layer for the mobile app and Garage pages."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

_STABILITY_PATCH = r"""
<style id="lexus-stability-css">
/* Keep the last card fully scrollable above the fixed iPhone navigation. */
body{scroll-padding-bottom:150px}
.shell{padding-bottom:155px!important}
.bottom-nav{transform:translateX(-50%) translateZ(0);-webkit-transform:translateX(-50%) translateZ(0)}
/* Some iOS/WebKit builds render inline SVG paths as black fills unless explicitly reset. */
.status-icon svg,.quick-icon svg,.round-button svg,.bottom-item svg{
  fill:none!important;stroke:currentColor!important;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round
}
.status-icon,.quick-icon,.round-button,.bottom-item{color:#a9d8ff}
/* Make Garage forms less fragile on narrow phones. */
@media(max-width:620px){
  #location-form,#maintenance-form{display:grid!important;grid-template-columns:1fr 1fr;gap:8px!important}
  #location-form button,#maintenance-form button,#maintenance-next{min-height:44px}
  #maintenance-next{grid-column:1/2}
  main{padding-bottom:110px!important}
}
/* Do not let stale/offline state visually cover controls forever. */
.error-banner{overflow-wrap:anywhere}
</style>
<script id="lexus-stability-js">
(()=>{
  const qs=(s,r=document)=>r.querySelector(s);
  const qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  const standalone=window.matchMedia?.('(display-mode: standalone)').matches||window.navigator.standalone===true;
  const privateHost=h=>/^192\.168\.|^10\.|^172\.(1[6-9]|2\d|3[01])\./.test(h||'');
  const parseDate=value=>{
    if(value===null||value===undefined)return null;
    let raw=String(value).trim();
    if(/^\d{10}(?:\.\d+)?$/.test(raw))raw=String(Number(raw)*1000);
    const n=Number(raw);
    const d=Number.isFinite(n)&&raw.length>=12?new Date(n):new Date(raw);
    return Number.isNaN(d.getTime())?null:d;
  };
  const prettyDate=value=>{
    const d=parseDate(value);if(!d)return null;
    return d.toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).replace(',',' at');
  };
  const iso=/\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b/g;
  const normalizeText=root=>{
    if(!root)return;
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
    nodes.forEach(node=>{
      const p=node.parentElement;if(!p||['SCRIPT','STYLE'].includes(p.tagName))return;
      const before=node.nodeValue||'';
      const after=before.replace(iso,m=>prettyDate(m)||m);
      if(after!==before)node.nodeValue=after;
    });
    const tire=qs('#tire-updated',root)||qs('#tire-updated');
    if(tire&&/^\d{10}(?:\.\d+)?$/.test(tire.textContent.trim())){
      tire.textContent=prettyDate(tire.textContent.trim())||'Latest reported';
    }
  };
  const svg={
    door:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 20V5.5A1.5 1.5 0 0 1 7.5 4h8A1.5 1.5 0 0 1 17 5.5V20"/><path d="M9 11h.01"/><path d="M4 20h16"/></svg>',
    window:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6h14l-1 12H6L5 6Z"/><path d="M7 9h10"/></svg>',
    lock:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>',
    tire:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 4v5m0 6v5M4 12h5m6 0h5"/></svg>'
  };
  const fixIcons=()=>{
    qsa('.status-card').forEach(card=>{
      const holder=qs('.status-icon',card);if(!holder||qs('svg',holder))return;
      const label=(qs('.status-name',card)?.textContent||'').toLowerCase();
      holder.innerHTML=label.includes('lock')?svg.lock:label.includes('window')?svg.window:svg.door;
    });
    qsa('.quick-card').forEach(card=>{
      const holder=qs('.quick-icon',card);if(!holder||qs('svg',holder))return;
      const label=(qs('.quick-label',card)?.textContent||'').toLowerCase();
      holder.innerHTML=label.includes('lock')?svg.lock:label.includes('window')?svg.window:svg.tire;
    });
  };
  const explainConnection=()=>{
    const actions=qs('#connection-actions');if(!actions)return;
    qsa('a',actions).forEach(a=>{
      try{
        const u=new URL(a.href,location.href);
        if(standalone&&privateHost(u.hostname)){
          a.textContent='Open Home LAN in Safari';
          a.target='_blank';a.rel='noopener';
        }
      }catch(_){ }
    });
    if(standalone&&!qs('.origin-note',actions.parentElement)){
      const n=document.createElement('div');n.className='origin-note';
      n.style.cssText='color:#91a3b5;font-size:.64rem;line-height:1.4;margin-top:7px';
      n.textContent='The installed app stays on its HTTPS Tailscale origin. Home LAN opens separately because iOS does not switch an installed web app between origins.';
      actions.parentElement.appendChild(n);
    }
  };
  const enhanceGarageInputs=()=>{
    const cost=qs('#maintenance-cost');if(cost)cost.inputMode='decimal';
    const due=qs('#maintenance-next');if(due)due.inputMode='numeric';
    const radius=qs('#location-radius');if(radius)radius.inputMode='numeric';
  };
  let scheduled=false;
  const run=()=>{
    scheduled=false;normalizeText(document.body);fixIcons();explainConnection();enhanceGarageInputs();
  };
  const schedule=()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(run)};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',run,{once:true});else run();
  new MutationObserver(schedule).observe(document.documentElement,{subtree:true,childList:true,characterData:true});
  window.addEventListener('pageshow',schedule);
  window.addEventListener('orientationchange',()=>setTimeout(()=>window.dispatchEvent(new Event('resize')),250));
})();
</script>
""".strip()


class StabilityMiddleware(BaseHTTPMiddleware):
    """Inject narrow, presentation-only stability fixes into /app and /garage."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path not in {"/app", "/garage"}:
            return response
        if "text/html" not in response.headers.get("content-type", ""):
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode("utf-8", errors="replace")
        if "lexus-stability-js" not in text and "</body>" in text:
            text = text.replace("</body>", f"{_STABILITY_PATCH}</body>", 1)

        headers = dict(response.headers)
        headers.pop("content-length", None)
        headers["Cache-Control"] = "no-cache"
        return Response(
            content=text,
            status_code=response.status_code,
            headers=headers,
            media_type="text/html",
        )
