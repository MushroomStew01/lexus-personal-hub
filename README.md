# Lexus Personal Hub

A read-only personal vehicle-data app with a Lexus dashboard, local trip history, fuel tracking, Discord commands, and optional alerts.

![Status](https://img.shields.io/badge/status-v0.3-black) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## v0.3

- full vehicle-status dashboard
- odometer, fuel, range and speed
- tire pressure for all reported tires
- doors, windows, moonroof, hood and trunk status
- door-lock status when Home Assistant exposes it
- next-service and source-update information when available
- local trip inference and 7/30-day driving analytics
- fuel fill-up history and 30-day fuel spend
- Toronto/local-time display using `TIMEZONE`
- Discord slash-command companion
- optional Discord webhook alerts

The project intentionally does **not** issue remote lock/unlock, remote-start, climate, hazard, or other vehicle-control commands.

## Architecture

```text
Lexus / Toyota Connected Services
             |
             v
       Home Assistant
             |
             v
     Lexus Personal Hub
       |      |      |
       v      v      v
 Dashboard  Trips  Discord
```

Two providers are included:

- `mock` — development/testing without vehicle credentials
- `home_assistant` — reads the owner's vehicle entities from the Home Assistant REST API

## Quick start

```bash
git clone https://github.com/MushroomStew01/lexus-personal-hub.git
cd lexus-personal-hub
python -m venv .venv
```

Linux/Raspberry Pi OS:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
lexus-hub serve --host 0.0.0.0
```

The default `PROVIDER=mock` works immediately.

## Connect Home Assistant

Create a Home Assistant long-lived access token and put it only in your private `.env`:

```dotenv
PROVIDER=home_assistant
HA_BASE_URL=http://homeassistant.local:8123
HA_TOKEN=
VEHICLE_DISPLAY_NAME=My Lexus
```

Discover the vehicle entities:

```bash
lexus-hub provider-discover
```

Test a live read without saving it:

```bash
lexus-hub provider-test
```

If automatic matching is ambiguous, configure explicit entities:

```dotenv
HA_ODOMETER_ENTITY=sensor.your_lexus_odometer
HA_FUEL_ENTITY=sensor.your_lexus_fuel_level
HA_RANGE_ENTITY=sensor.your_lexus_distance_to_empty
HA_SPEED_ENTITY=sensor.your_lexus_speed
```

Save one snapshot:

```bash
lexus-hub poll-once
```

While the web app is running, snapshots are collected automatically according to `POLL_INTERVAL_MINUTES`.

## Dashboard

Run:

```bash
lexus-hub serve --host 0.0.0.0
```

Open:

```text
http://<device-ip>:8000
```

Useful endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Health check |
| `POST /api/poll` | Fetch and save one snapshot |
| `GET /api/status` | Latest saved status and summary |
| `GET /api/provider/test` | Live provider test without saving |
| `GET /api/provider/discover` | Home Assistant entity discovery |
| `GET /api/trips` | Recent inferred trips |
| `GET /api/distance?days=30` | Daily distance series |
| `GET /api/fuel` | Recent fill-ups |
| `POST /api/fuel` | Log a fill-up |

Interactive API docs are at `/docs`.

## Discord bot

Create a Discord application/bot and keep its token only in `.env`:

```dotenv
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
```

If you have a private remote dashboard address, optionally set:

```dotenv
DASHBOARD_URL=
```

Run the bot as a separate process/container that shares the same `.data` directory as the web app:

```bash
lexus-hub bot
```

Commands:

- `/car` — latest saved vehicle summary
- `/tires` — tire pressures
- `/doors` — door/window/body-opening status
- `/locks` — saved lock status
- `/dashboard` — configured private dashboard URL
- `/refresh` — read Home Assistant and save a fresh local snapshot
- `/trips` — five most recent inferred trips
- `/fuel` — log a fuel fill-up

All bot responses are ephemeral by default.

## Automatic Discord alerts

A Discord webhook can be configured separately from the slash-command bot:

```dotenv
DISCORD_WEBHOOK_URL=
LOW_FUEL_PERCENT=20
LOW_RANGE_KM=80
LAST_SERVICE_ODOMETER_KM=
SERVICE_INTERVAL_KM=8000
```

The current released alert engine covers low fuel, low range and maintenance reminders. Additional v0.3 status fields are already persisted for future alert rules.

## Trip detection

Trips are inferred from odometer movement. A trip starts when odometer movement reaches `MIN_TRIP_DELTA_KM` and closes after `TRIP_IDLE_CLOSE_MINUTES` without further movement. Large snapshot gaps beyond `MAX_SNAPSHOT_GAP_HOURS` are not treated as known continuous travel.

Because Connected Services/Home Assistant telemetry is polled rather than streamed continuously, trip timestamps are approximate. Distance is based on odometer deltas.

## Fuel tracking

Example API request:

```bash
curl -X POST http://127.0.0.1:8000/api/fuel \
  -H "Content-Type: application/json" \
  -d '{"liters":42.5,"total_cost":67.95,"odometer_km":54631}'
```

## Docker on Raspberry Pi OS

Build the image:

```bash
docker build -t lexus-personal-hub .
mkdir -p .data
```

Web dashboard:

```bash
docker run -d \
  --name lexus-personal-hub \
  --restart unless-stopped \
  --env-file .env \
  --network host \
  -v "$PWD/.data:/app/.data" \
  lexus-personal-hub
```

Discord bot:

```bash
docker run -d \
  --name lexus-personal-hub-bot \
  --restart unless-stopped \
  --env-file .env \
  --network host \
  -v "$PWD/.data:/app/.data" \
  lexus-personal-hub \
  lexus-hub bot
```

SQLite uses WAL mode, so the dashboard and Discord bot can share the same local database.

## Private remote access

The dashboard should remain private. A simple deployment pattern is to run Tailscale on the Raspberry Pi and on the phone/laptop used to access the dashboard, then browse to the Pi's Tailscale address on port `8000`.

Do not expose port `8000` directly to the public internet. If a public reverse proxy is ever added, add application authentication and TLS first.

## Privacy and security

- keep Home Assistant and Discord credentials in `.env` or another secret manager
- `.env`, `.data/`, databases and logs are ignored by Git
- never commit access tokens, VINs, trip databases, exact location exports or webhook URLs
- `STORE_LOCATION=false` by default
- the app reads vehicle state; it does not issue vehicle-control commands
- prefer private-network access such as Tailscale instead of public port forwarding

See `SECURITY.md` for the repository security policy.

## Tests

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

GitHub Actions runs linting and tests on Python 3.11 and 3.12.

## Disclaimer

This project is independent and is not affiliated with, endorsed by, or sponsored by Lexus, Toyota, Home Assistant, Discord, or Tailscale.
