# Lexus Garage features

The `/garage` page layers driving intelligence on top of the read-only Home Assistant telemetry bridge. The `/app` page is the installable mobile-first companion.

## Included

1. **Trip replay** — stored GPS snapshots, odometer, fuel percentage, speed, and time can be replayed with a MapLibre slider.
2. **Named locations and privacy zones** — save the Lexus's current location as Home, Work, etc. Private zones are shown as `Private location` in trip/parking notifications.
3. **Where's My Lexus?** — latest stored location, parked-since time, fuel, range, and a private MapLibre map.
4. **Fuel analytics** — fill-to-fill L/100 km, cost/km, 30-day fuel spend, and litres.
5. **Vehicle timeline** — trips, fuel fills, maintenance, and door/window/lock changes are combined into one activity feed.
6. **Smarter Discord alerts** — low fuel, low range, low tire pressure, stale telemetry, and optional parked-open / parked-unlocked warnings.
7. **Trip-complete Discord summaries** — completed trips can post start/end labels, distance, duration, and the private dashboard link.
8. **Weekly Discord report** — seven-day distance, trip count, average/longest trip, fuel spend, and current tire pressures.
9. **Maintenance history** — log service type, odometer, cost, notes, and next-due odometer from Discord or REST.
10. **Vehicle Health Score** — a 0–100 telemetry-readiness score covering freshness, tires, parked security, fuel/range, and service due status. It is not a mechanical diagnostic score.
11. **Installable phone app / PWA** — `/app` has its own manifest, 192/512 icons, service worker, standalone display mode, mobile navigation, health score, current telemetry, parking summary, and recent trips.

## Private Pi settings

Keep real values in `.env`; do not commit them.

```dotenv
STORE_LOCATION=true
SHOW_EXACT_LOCATION=true
HA_LOCATION_ENTITY=device_tracker.your_lexus_current_location
NAMED_LOCATION_DEFAULT_RADIUS_M=250
PARKING_SPEED_THRESHOLD_KPH=1

LOW_TIRE_PSI=30
ALERT_OPENINGS=false
ALERT_UNLOCKED=false
STALE_TELEMETRY_MINUTES=180
TRIP_SUMMARY_ENABLED=true
WEEKLY_REPORT_ENABLED=true
WEEKLY_REPORT_WEEKDAY=6
WEEKLY_REPORT_HOUR=19

DISCORD_WEBHOOK_URL=
```

`WEEKLY_REPORT_WEEKDAY` uses Python weekday numbering: Monday `0` through Sunday `6`.

Automatic alerts, trip summaries, and weekly reports currently use `DISCORD_WEBHOOK_URL`. Slash commands use `DISCORD_BOT_TOKEN`.

## Pages

- `/` — full vehicle status dashboard
- `/app` — installable mobile Lexus Hub
- `/garage` — trip replay and driving intelligence
- `/docs` — FastAPI REST documentation

## Vehicle Health Score

`GET /api/health-score` returns the score, grade, attention count, and individual readiness checks. The scoring engine currently considers:

- Lexus telemetry freshness
- four reported tire pressures
- doors/windows/body openings while parked
- lock state while parked
- fuel percentage and range
- configured service interval or Toyota's next-service sensor

Missing sensors are reported as unknown rather than automatically treated as vehicle faults.

## Installing the mobile app

The PWA lives at `/app`. Service workers require a secure browser context, so use a private HTTPS address for installation rather than exposing port 8000 directly to the public internet.

With Tailscale already running on the Pi, a private HTTPS endpoint can be published to the tailnet with:

```bash
sudo tailscale serve --bg 8000
tailscale serve status
```

Open the resulting private HTTPS URL and add `/app`.

- iPhone/iPad: open `/app` in Safari, tap **Share**, then **Add to Home Screen**.
- Browsers that expose the install prompt will show the app's **Install** button.

The service worker caches only the app shell, manifest, and icons. `/api/*` vehicle data is deliberately network-only so stale telemetry/location is not served from the PWA cache.

## REST endpoints

- `GET /api/health-score`
- `GET /api/where`
- `GET /api/locations`
- `POST /api/locations/current`
- `GET /api/trips/{trip_id}/route`
- `GET /api/trips/{trip_id}/replay`
- `GET /api/fuel/analytics`
- `GET /api/timeline`
- `GET /api/maintenance`
- `POST /api/maintenance`
- `GET /api/weekly`

Exact trip/replay coordinates require both `STORE_LOCATION=true` and `SHOW_EXACT_LOCATION=true`.

## Discord commands

Alongside the original `/car`, `/tires`, `/doors`, `/locks`, `/refresh`, `/trips`, `/fuel`, and `/dashboard` commands, the bot now includes:

- `/where`
- `/locations`
- `/location_add`
- `/timeline`
- `/fuelstats`
- `/maintenance`
- `/maintenance_add`
- `/weekly`

## Updating the Raspberry Pi

```bash
cd ~/lexus-personal-hub
git checkout main
git pull

docker rm -f lexus-personal-hub lexus-personal-hub-bot 2>/dev/null || true
docker build -t lexus-personal-hub .

docker run -d \
  --name lexus-personal-hub \
  --restart unless-stopped \
  --env-file .env \
  --network host \
  -v "$PWD/.data:/app/.data" \
  lexus-personal-hub

docker run -d \
  --name lexus-personal-hub-bot \
  --restart unless-stopped \
  --env-file .env \
  --network host \
  -v "$PWD/.data:/app/.data" \
  lexus-personal-hub \
  lexus-hub bot
```

`init_db()` creates the new `named_locations` and `maintenance_records` tables automatically. Existing trip, fuel, and snapshot history is preserved.

## Privacy

The SQLite database remains local under `.data/` and is ignored by Git. Named private zones do not expose their names in trip/parking summaries. Exact route/replay APIs remain disabled unless `SHOW_EXACT_LOCATION=true` is explicitly enabled.

The PWA does not cache `/api/*` responses. The MapLibre page uses OpenStreetMap raster tiles. The existing route view may also use the configured OSRM server for road-line estimation, which can receive the sampled route coordinates when that map is opened.
