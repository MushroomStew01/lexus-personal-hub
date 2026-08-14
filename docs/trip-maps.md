# Trip maps

Lexus Personal Hub can store the vehicle location reported by Home Assistant and use it to build a private trip map.

## Privacy

Trip coordinates are stored only in the local application database. The database and `.env` are gitignored and should remain on the Raspberry Pi.

Trip map coordinates are exposed by the dedicated trip-route API only when both settings are enabled:

```dotenv
STORE_LOCATION=true
SHOW_EXACT_LOCATION=true
```

Keep the dashboard private (for example behind Tailscale). Do not expose the trip-route API publicly without adding application-level authentication.

## Home Assistant source

The Home Assistant provider uses `HA_LOCATION_ENTITY` when configured. If it is blank, the provider tries, in order:

1. Current Location
2. Last Parked Location
3. Parking Location

The Toyota North America integration exposes these as GPS device tracker entities when the account/vehicle supports them.

## Route rendering

The dashboard uses MapLibre GL JS with OpenStreetMap raster tiles. Stored Lexus GPS points are sent from the local route endpoint to the browser.

For the road line, the browser asks the configured router for an estimated driving route through a sampled subset of the stored points:

```dotenv
MAP_ROUTER_URL=https://router.project-osrm.org
```

If the router is unavailable, the dashboard falls back to connecting the stored Lexus GPS samples directly.

The displayed road line is an estimate. Toyota/Lexus cloud telemetry is not a high-frequency GPS trace, so it should not be treated as an exact turn-by-turn record of the vehicle's path.

## Existing trips

Trips created before location storage was enabled do not gain location history retroactively. New route data begins with snapshots saved after `STORE_LOCATION=true` is enabled.
