from __future__ import annotations

import asyncio
import json
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .ha_refresh import discover_refresh_options, request_vehicle_refresh
from .poller import poll_once
from .providers import get_provider

router = APIRouter(tags=["mobile resilience"])


def _host(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.hostname


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def _provider_source_timestamp() -> datetime | None:
    settings = get_settings()
    provider = get_provider(settings)
    reading = await provider.fetch()
    return reading.source_updated_at


@router.get("/api/vehicle/refresh-capability")
async def api_vehicle_refresh_capability() -> dict[str, object]:
    settings = get_settings()
    try:
        result = await discover_refresh_options(settings)
        result["off_vehicle_refresh"] = bool(
            result.get("selected_service") == "toyota_na.refresh"
            and result.get("configured_device_id")
        )
        result["off_vehicle_note"] = (
            "toyota_na.refresh is a telemetry wake/status-refresh request. It can be requested "
            "while the car is off; success still depends on Toyota Connected Services and the "
            "vehicle cellular modem responding. It does not start the engine."
        )
        return result
    except Exception as exc:
        return {
            "supported": False,
            "reason": f"Refresh discovery failed: {exc}",
        }


@router.post("/api/vehicle/refresh")
async def api_vehicle_refresh() -> dict[str, object]:
    settings = get_settings()
    before_source: datetime | None = None
    try:
        before_source = await _provider_source_timestamp()
    except Exception:
        # The actual refresh request can still succeed even if the pre-flight read fails.
        pass

    refresh_result: dict[str, object]
    try:
        refresh_result = await request_vehicle_refresh(settings)
    except Exception as exc:
        refresh_result = {
            "requested": False,
            "reason": f"Vehicle wake/refresh request failed: {exc}",
        }

    # The Toyota NA Home Assistant service already waits for its own coordinator refresh.
    # After it returns, probe Home Assistant a few times without issuing another wake command.
    # This verifies whether the parked/off vehicle actually uploaded a newer telemetry revision.
    after_source: datetime | None = None
    fresh_data_received = False
    verification_attempts = 0
    if refresh_result.get("requested"):
        wait_budget = max(0, settings.ha_refresh_settle_seconds)
        delays = [0, 3, 5, 7, 10]
        elapsed = 0
        for delay in delays:
            if delay:
                if elapsed + delay > wait_budget:
                    break
                await asyncio.sleep(delay)
                elapsed += delay
            verification_attempts += 1
            try:
                after_source = await _provider_source_timestamp()
            except Exception:
                continue
            if after_source is not None and (
                before_source is None or after_source > before_source
            ):
                fresh_data_received = True
                break

    poll_result = await poll_once(settings)
    poll_source_text = poll_result.get("source_updated_at")
    if isinstance(poll_source_text, str):
        try:
            poll_source = datetime.fromisoformat(poll_source_text)
        except ValueError:
            poll_source = None
        if poll_source is not None:
            after_source = poll_source
            if before_source is None or poll_source > before_source:
                fresh_data_received = True

    if not refresh_result.get("requested"):
        refresh_state = "request_failed"
    elif fresh_data_received:
        refresh_state = "fresh_vehicle_data_received"
    else:
        refresh_state = "refresh_requested_no_new_vehicle_timestamp"

    return {
        "refresh": refresh_result,
        "verification": {
            "state": refresh_state,
            "fresh_data_received": fresh_data_received,
            "before_source_updated_at": _iso(before_source),
            "after_source_updated_at": _iso(after_source),
            "attempts": verification_attempts,
            "vehicle_may_be_asleep": bool(
                refresh_result.get("requested") and not fresh_data_received
            ),
        },
        "poll": poll_result,
        "note": (
            "This action asks Toyota Connected Services to wake/refresh vehicle telemetry and "
            "then verifies whether the Toyota telemetry timestamp advanced. The request can be "
            "made while the car is off, but a deeply sleeping or unreachable vehicle may not "
            "return newer data. It does not start, lock, unlock, or change climate settings."
        ),
    }


class MobileResilienceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # noqa: ANN001
        response = await call_next(request)
        if request.url.path != "/app" or "text/html" not in response.headers.get(
            "content-type", ""
        ):
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        text = body.decode("utf-8", errors="replace")

        settings = get_settings()
        access = {
            "local_url": settings.local_dashboard_url,
            "remote_url": settings.dashboard_url,
            "local_host": _host(settings.local_dashboard_url),
            "remote_host": _host(settings.dashboard_url),
        }
        access_json = json.dumps(access).replace("</", "<\\/")
        inline = f"""
<script>
window.LEXUS_CONNECTIONS = {access_json};
(() => {{
  const config = window.LEXUS_CONNECTIONS || {{}};
  const make = (tag, cls, text) => {{
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  }};

  function addStyles() {{
    if (document.querySelector('#lexus-resilience-style')) return;
    const style = document.createElement('style');
    style.id = 'lexus-resilience-style';
    style.textContent = `
      .quick-actions{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
      .quick-action{{border:1px solid #38516a;background:#162535;color:#a9d8ff;border-radius:10px;
        padding:8px 10px;font:inherit;cursor:pointer;text-decoration:none;font-size:.78rem}}
      .quick-action:disabled{{opacity:.55;cursor:wait}}
      .connection-actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}
      .connection-actions a{{display:inline-block;border:1px solid #38516a;background:#162535;
        color:#a9d8ff;border-radius:10px;padding:8px 10px;text-decoration:none;font-size:.78rem}}
      .connection-note{{color:#8ea0b2;font-size:.7rem;line-height:1.45;margin-top:8px}}
    `;
    document.head.appendChild(style);
  }}

  function addRefreshButton() {{
    const header = document.querySelector('header');
    if (!header || document.querySelector('#vehicle-refresh-button')) return;
    let actions = header.querySelector('.quick-actions');
    if (!actions) {{
      actions = make('div', 'quick-actions');
      header.appendChild(actions);
    }}
    const button = make('button', 'quick-action', '↻ Refresh');
    button.id = 'vehicle-refresh-button';
    button.addEventListener('click', async () => {{
      button.disabled = true;
      button.textContent = 'Waking Lexus…';
      try {{
        const response = await fetch('/api/vehicle/refresh', {{method: 'POST', cache: 'no-store'}});
        if (!response.ok) throw new Error(await response.text());
        const result = await response.json();
        button.textContent = result.verification?.fresh_data_received ? 'Fresh data ✓' : 'Refresh requested';
        setTimeout(() => window.location.reload(), 900);
      }} catch (_) {{
        button.textContent = 'Refresh failed';
        button.disabled = false;
      }}
    }});
    actions.appendChild(button);
  }}

  function addConnectionCard() {{
    if (document.querySelector('#connection-card') || document.querySelector('#connection-fallback-card')) return;
    const grid = document.querySelector('section.grid');
    if (!grid || (!config.local_url && !config.remote_url)) return;
    const card = make('article', 'card');
    card.id = 'connection-fallback-card';
    card.appendChild(make('h2', '', 'Connection'));
    const hostname = window.location.hostname;
    const mode = hostname === config.local_host ? 'Home LAN' :
      (hostname === config.remote_host ? 'Tailscale / private' : 'Current route');
    card.appendChild(make('div', 'where-main', mode));
    card.appendChild(make('div', 'sub', window.location.origin));

    const actions = make('div', 'connection-actions');
    if (config.local_url) {{
      const local = make('a', '', 'Use Home LAN');
      local.href = config.local_url;
      actions.appendChild(local);
    }}
    if (config.remote_url) {{
      const remote = make('a', '', 'Use Tailscale');
      remote.href = config.remote_url;
      actions.appendChild(remote);
    }}
    card.appendChild(actions);
    card.appendChild(make(
      'div',
      'connection-note',
      'The installed HTTPS app keeps its Tailscale origin. Home LAN is offered as a direct link; '
        + 'a transparent HTTPS-to-HTTP switch is intentionally not attempted.'
    ));
    grid.appendChild(card);
  }}

  function improveUnavailableMessage() {{
    const status = document.querySelector('#statusline');
    if (status && status.textContent.trim() === 'Connection unavailable') {{
      status.textContent = 'Vehicle data unavailable on this route — try the connection options above.';
    }}
  }}

  function init() {{
    addStyles();
    addRefreshButton();
    setTimeout(() => {{ addConnectionCard(); improveUnavailableMessage(); }}, 650);
  }}

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {{once:true}});
  else init();
}})();
</script>
""".strip()

        if "window.LEXUS_CONNECTIONS" not in text and "</body>" in text:
            text = text.replace("</body>", f"{inline}\n</body>", 1)

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=text,
            status_code=response.status_code,
            headers=headers,
            media_type="text/html",
        )
