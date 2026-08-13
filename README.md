# Lexus Personal Hub

A read-only personal vehicle-data app with a Lexus dashboard, local trip history, fuel tracking, and optional Discord alerts.

![Status](https://img.shields.io/badge/status-v0.2-black) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## What it does

- polls vehicle telemetry on a configurable interval
- stores odometer, fuel level, estimated range, and speed in local SQLite
- infers trips from odometer movement
- shows 7-day and 30-day distance totals
- logs fuel fill-ups and 30-day fuel spend
- sends optional low-fuel, low-range, and service-due Discord webhook alerts
- provides `/car`, `/trips`, and `/fuel` Discord slash commands
- exposes a FastAPI dashboard and JSON API

The project intentionally does **not** issue remote vehicle-control commands.

## Provider design

Two providers are included:

- `mock` — works immediately for development and testing
- `home_assistant` — reads the owner's Lexus telemetry through the Home Assistant REST API

Home Assistant is the recommended real-data boundary. It keeps this application independent from changes to the upstream Toyota/Lexus account integration.

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

## Quick start

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

Open `http://127.0.0.1:8000`. The default `PROVIDER=mock` works without vehicle credentials.

## Connect real Lexus data

Set up a Home Assistant Toyota/Lexus integration first and confirm Home Assistant exposes the vehicle's odometer. Then create a Home Assistant long-lived access token and update your private `.env`:

```dotenv
PROVIDER=home_assistant
HA_BASE_URL=http://homeassistant.local:8123
HA_TOKEN=your_private_home_assistant_token
VEHICLE_DISPLAY_NAME=My Lexus
```

Inspect candidate entities without saving vehicle data:

```bash
lexus-hub provider-discover
```

Test a live read:

```bash
lexus-hub provider-test
```

If automatic matching is ambiguous, configure explicit entity IDs:

```dotenv
HA_ODOMETER_ENTITY=sensor.your_lexus_odometer
HA_FUEL_ENTITY=sensor.your_lexus_fuel_level
HA_RANGE_ENTITY=sensor.your_lexus_distance_to_empty
HA_SPEED_ENTITY=sensor.your_lexus_speed
```

Only odometer is required. The current Home Assistant provider does not request or store vehicle location.

Save a snapshot manually with:

```bash
lexus-hub poll-once
```

When `lexus-hub serve` is running, the app also polls automatically using `POLL_INTERVAL_MINUTES`.

## Trip detection

Trips are inferred from odometer changes. A trip begins when movement reaches `MIN_TRIP_DELTA_KM`, continues while the odometer increases, and closes after `TRIP_IDLE_CLOSE_MINUTES` without movement. Large gaps beyond `MAX_SNAPSHOT_GAP_HOURS` are not treated as continuous known history.

The default 15-minute polling interval means trip start/end timestamps are approximate. Distance is based on odometer differences.

## Fuel tracking

Log a fill-up through the API:

```bash
curl -X POST http://127.0.0.1:8000/api/fuel \
  -H "Content-Type: application/json" \
  -d '{"liters":42.5,"total_cost":67.95,"odometer_km":42821}'
```

## Discord

For automatic alerts, set:

```dotenv
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

For slash commands, set:

```dotenv
DISCORD_BOT_TOKEN=...
DISCORD_GUILD_ID=123456789012345678
```

Then run:

```bash
lexus-hub bot
```

Commands:

- `/car` — latest saved status and 7-day distance
- `/trips` — five most recent inferred trips
- `/fuel` — log a fill-up

## REST API

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Health check |
| `POST /api/poll` | Fetch and save one snapshot |
| `GET /api/status` | Latest saved status and summary |
| `GET /api/provider/test` | Test live provider without saving |
| `GET /api/provider/discover` | Show source entity candidates |
| `GET /api/trips` | Recent inferred trips |
| `GET /api/distance?days=30` | Daily distance series |
| `GET /api/fuel` | Recent fill-ups |
| `POST /api/fuel` | Log a fill-up |

Interactive API docs are at `/docs`.

## Maintenance alerts

```dotenv
LAST_SERVICE_ODOMETER_KM=40000
SERVICE_INTERVAL_KM=8000
LOW_FUEL_PERCENT=20
LOW_RANGE_KM=80
```

## Docker

Build and run directly with Docker:

```bash
docker build -t lexus-personal-hub .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env \
  -v "${PWD}/.data:/app/.data" lexus-personal-hub
```

## Privacy and security

- keep real credentials in `.env` or another secret manager
- `.env`, `.data/`, databases, and logs are ignored by Git
- do not commit access tokens, VINs, trip databases, or vehicle exports
- the Home Assistant provider does not request location
- bind locally unless you intentionally add authentication and TLS

See `SECURITY.md` for the repository security policy.

## Tests

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

GitHub Actions runs linting and tests on Python 3.11 and 3.12.

## Disclaimer

This project is independent and is not affiliated with, endorsed by, or sponsored by Lexus, Toyota, Home Assistant, or Discord.
