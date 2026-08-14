from __future__ import annotations

import argparse
import asyncio
import json
import logging

import uvicorn

from .config import get_settings
from .db import init_db
from .poller import poll_once
from .providers import get_provider


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lexus-hub")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the dashboard and REST API")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")

    sub.add_parser("poll-once", help="Fetch and save one vehicle snapshot")
    sub.add_parser("provider-discover", help="Show matching provider entities")
    sub.add_parser("provider-test", help="Fetch current telemetry without saving it")
    sub.add_parser("bot", help="Run the Discord slash-command bot")
    sub.add_parser("init-db", help="Create local database tables")
    return parser


async def _discover() -> None:
    provider = get_provider(get_settings())
    print(json.dumps(await provider.discover(), indent=2, default=str))


async def _test() -> None:
    provider = get_provider(get_settings())
    reading = await provider.fetch()
    output = {
        "provider": provider.name,
        "vehicle": reading.display_name,
        "observed_at": reading.observed_at,
        "odometer_km": reading.odometer_km,
        "fuel_percent": reading.fuel_percent,
        "range_km": reading.range_km,
        "speed_kph": reading.speed_kph,
        "status": reading.raw.get("status", {}),
    }
    print(json.dumps(output, indent=2, default=str))


def main() -> None:
    args = _parser().parse_args()
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "serve":
        uvicorn.run(
            "lexus_hub.app:app",
            host=args.host or settings.app_host,
            port=args.port or settings.app_port,
            reload=args.reload,
        )
    elif args.command == "poll-once":
        print(json.dumps(asyncio.run(poll_once(settings)), indent=2, default=str))
    elif args.command == "provider-discover":
        asyncio.run(_discover())
    elif args.command == "provider-test":
        asyncio.run(_test())
    elif args.command == "bot":
        from .bot import run_bot

        run_bot(settings)
    elif args.command == "init-db":
        init_db()
        print("Database initialized.")
