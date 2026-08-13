# Lexus Personal Hub

An open-source personal vehicle-data application combining three projects:

1. **Lexus personal dashboard** — odometer, fuel/range, maintenance interval, fuel spend and driving analytics.
2. **Lexus → Discord** — low-fuel/range/service alerts plus `/car`, `/trips` and `/fuel` slash commands.
3. **Lexus trip logger** — stores vehicle snapshots and infers trips from odometer movement.

The vehicle integration is intentionally **read-only telemetry**. The application does not issue vehicle-control commands.

![Status](https://img.shields.io/badge/status-v0.1-black) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## Provider design

Lexus/Toyota Connected Services in North America does not provide a simple public owner API that this project can safely depend on. The app therefore uses a provider interface:

- `mock` — works immediately for development and testing.
- `home_assistant` — reads vehicle entities from a Home Assistant instance through its REST API.

The dashboard, database, trip detection, analytics and Discord features remain independent of the upstream vehicle-data source.

## Architecture

```text
           Vehicle data source
                    │
                    ▼
             Vehicle Provider
         ┌──────────┴──────────┐
         │                     │
      mock mode        Home Assistant REST
                               │
                    ┌──────────▼──────────┐
                    │ Snapshot Poller     │
                    └──────────┬──────────┘
                               │
                         SQLite / SQL
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
       FastAPI dashboard   Trip detector    Discord alerts/bot
```

## Quick start — demo mode

```bash
git clone https://github.com/MushroomStew01/lexus-personal-hub.git
cd lexus-personal-hub
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
lexus-hub serve --reload
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
lexus-hub serve --reload
```

Open `http://127.0.0.1:8000`. The default `PROVIDER=mock` lets you use the full app without vehicle credentials.

Force a snapshot:

```bash
lexus-hub poll-once
```

## Connect a real Lexus through Home Assistant

The app can consume Home Assistant entities exposing odometer, fuel, range, location, speed and last-update time.

Create a Home Assistant long-lived access token, then change your local `.env`:

```dotenv
PROVIDER=home_assistant
HA_BASE_URL=http://homeassistant.local:8123
HA_TOKEN=your_long_lived_token

HA_ODOMETER_ENTITY=sensor.your_lexus_odometer
HA_FUEL_ENTITY=sensor.your_lexus_fuel_level
HA_RANGE_ENTITY=sensor.your_lexus_fuel_range
HA_LOCATION_ENTITY=device_tracker.your_lexus
HA_SPEED_ENTITY=sensor.your_lexus_speed
HA_LAST_UPDATE_ENTITY=sensor.your_lexus_last_update
```

Only `HA_ODOMETER_ENTITY` is mandatory. Missing optional entities appear as blank values. The adapter converts miles → kilometres and mph → km/h when those units are supplied.

### Find your entity IDs

In Home Assistant: **Developer Tools → States**, search for the vehicle name and copy the relevant entity IDs into `.env`.

## Discord

### Automatic alerts

Set a Discord channel webhook in your local `.env`:

```dotenv
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

The poller can notify you when fuel falls below `LOW_FUEL_PERCENT`, estimated range falls below `LOW_RANGE_KM`, or the configured service interval is close. Alerts are de-duplicated.

### Slash-command bot

Set:

```dotenv
DISCORD_BOT_TOKEN=...
DISCORD_GUILD_ID=123456789012345678
```

Run:

```bash
lexus-hub bot
```

Commands:

- `/car` — latest odometer, fuel, range and 7-day distance
- `/trips` — five most recent detected trips
- `/fuel liters total_cost odometer_km` — log a fill-up

## Trip detection

A trip is inferred when the odometer increases by at least `MIN_TRIP_DELTA_KM` between snapshots. Consecutive moving snapshots are merged into one open trip. The trip closes after no odometer movement for `TRIP_IDLE_CLOSE_MINUTES`.

With a 15-minute poll interval, trip start/end times are approximate; distance is based on odometer differences.

## Fuel costs

Fuel fill-ups can be logged from the dashboard form, `POST /api/fuel`, or Discord `/fuel`.

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/fuel \
  -H "Content-Type: application/json" \
  -d '{"liters":42.5,"total_cost":67.95,"odometer_km":42821}'
```

## Maintenance

```dotenv
LAST_SERVICE_ODOMETER_KM=40000
SERVICE_INTERVAL_KM=8000
```

## REST API

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Health check |
| `POST /api/poll` | Request one data refresh |
| `GET /api/status` | Current vehicle + 7/30-day stats |
| `GET /api/trips` | Recent trips |
| `GET /api/distance?days=30` | Daily distance series |
| `POST /api/fuel` | Log a fill-up |

Interactive API docs are at `/docs`.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

To also run the Discord bot:

```bash
docker compose --profile bot up --build
```

## Secrets, data and privacy

This repository is designed so the source code can remain public while runtime credentials and personal vehicle data stay private.

- Keep real credentials in a local `.env`, deployment environment variables, or GitHub Actions repository secrets — never in tracked source files.
- `.env` is ignored by Git; `.env.example` contains placeholders only.
- SQLite data lives in `.data/` and is ignored by Git.
- Location collection is **off by default** with `STORE_LOCATION=false`.
- To opt into location history, explicitly set `STORE_LOCATION=true` in your private runtime configuration.
- Coordinates remain hidden from the status API unless `SHOW_EXACT_LOCATION=true`.
- Do not commit VINs, trip databases, exported location history, account credentials, session tokens, or Discord credentials.
- Bind to `127.0.0.1` unless you deliberately place the app behind authentication and TLS.

If a credential is accidentally committed, revoke/rotate it immediately; deleting the current file is not enough because Git history may still contain it.

## Tests

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

GitHub Actions runs linting and tests on Python 3.11 and 3.12 with read-only repository contents permission.

## Roadmap

- [ ] Real-world entity auto-discovery for common Home Assistant Lexus/Toyota integrations
- [ ] Route map view with privacy zones
- [ ] Fuel-economy calculations from full-tank fill-ups
- [ ] Monthly Discord driving report
- [ ] PostgreSQL deployment preset
- [ ] Export to CSV/Power BI
- [ ] Additional legitimate vehicle-data providers as regional support becomes available

## Disclaimer

This project is independent and is not affiliated with, endorsed by, or sponsored by Lexus, Toyota, Home Assistant, or Discord. Vehicle-data availability depends on vehicle, region, subscriptions and upstream integrations.
