from __future__ import annotations

"""Discord commands for the account owner's locally stored vehicle data."""

import discord
from discord import app_commands

from .analytics import recent_trips, status_summary
from .config import Settings
from .db import init_db, session_scope
from .poller import poll_once
from .storage import add_fuel_fill, primary_vehicle

_TIRE_LABELS = {
    "front_driver_tire": "Front driver",
    "front_passenger_tire": "Front passenger",
    "rear_driver_tire": "Rear driver",
    "rear_passenger_tire": "Rear passenger",
}
_SECURITY_LABELS = {
    "front_driver_door": "Front driver door",
    "front_passenger_door": "Front passenger door",
    "rear_driver_door": "Rear driver door",
    "rear_passenger_door": "Rear passenger door",
    "front_driver_window": "Front driver window",
    "front_passenger_window": "Front passenger window",
    "rear_driver_window": "Rear driver window",
    "rear_passenger_window": "Rear passenger window",
    "moonroof": "Moonroof",
    "hood": "Hood",
    "trunk": "Trunk",
}
_LOCK_LABELS = {
    "front_driver_door_lock": "Front driver",
    "front_passenger_door_lock": "Front passenger",
    "rear_driver_door_lock": "Rear driver",
    "rear_passenger_door_lock": "Rear passenger",
    "trunk_door_lock": "Trunk",
}


class LexusBot(discord.Client):
    def __init__(self, settings: Settings):
        super().__init__(intents=discord.Intents.none())
        self.settings = settings
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


def _status(settings: Settings) -> dict[str, object]:
    with session_scope() as session:
        return status_summary(session, settings)


def _fmt(value: object, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.1f}{suffix}"
    return f"{value}{suffix}"


def _record_value(status: dict[str, object], key: str) -> str:
    vehicle_status = status.get("vehicle_status")
    if not isinstance(vehicle_status, dict):
        return "—"
    record = vehicle_status.get(key)
    if not isinstance(record, dict):
        return "—"
    return str(record.get("display") or record.get("value") or "—")


def _status_embed(settings: Settings) -> discord.Embed:
    status = _status(settings)
    embed = discord.Embed(title=settings.vehicle_display_name, color=0xD4D4D4)
    if not status.get("ready"):
        embed.description = "No saved vehicle data yet."
        return embed

    embed.add_field(name="Odometer", value=_fmt(status.get("odometer_km"), " km"), inline=True)
    embed.add_field(name="Fuel", value=_fmt(status.get("fuel_percent"), "%"), inline=True)
    embed.add_field(name="Range", value=_fmt(status.get("range_km"), " km"), inline=True)
    embed.add_field(name="Speed", value=_fmt(status.get("speed_kph"), " km/h"), inline=True)
    embed.add_field(
        name="7-day distance",
        value=_fmt(status.get("distance_7d_km"), " km"),
        inline=True,
    )
    embed.add_field(
        name="30-day distance",
        value=_fmt(status.get("distance_30d_km"), " km"),
        inline=True,
    )
    last_poll = status.get("last_poll")
    if last_poll:
        embed.set_footer(text=f"Last saved snapshot: {last_poll}")
    return embed


def _records_text(
    settings: Settings,
    labels: dict[str, str],
) -> str:
    status = _status(settings)
    return "\n".join(
        f"**{label}:** {_record_value(status, key)}"
        for key, label in labels.items()
    )


def run_bot(settings: Settings) -> None:
    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required for `lexus-hub bot`.")
    init_db()
    bot = LexusBot(settings)

    @bot.tree.command(name="car", description="Show the latest saved Lexus status")
    async def car(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=_status_embed(settings), ephemeral=True)

    @bot.tree.command(name="tires", description="Show current Lexus tire pressures")
    async def tires(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            _records_text(settings, _TIRE_LABELS),
            ephemeral=True,
        )

    @bot.tree.command(name="doors", description="Show saved door and window status")
    async def doors(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            _records_text(settings, _SECURITY_LABELS),
            ephemeral=True,
        )

    @bot.tree.command(name="locks", description="Show saved Lexus lock status")
    async def locks(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            _records_text(settings, _LOCK_LABELS),
            ephemeral=True,
        )

    @bot.tree.command(name="dashboard", description="Open the private Lexus dashboard")
    async def dashboard(interaction: discord.Interaction) -> None:
        if not settings.dashboard_url:
            await interaction.response.send_message(
                "DASHBOARD_URL is not configured yet.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(settings.dashboard_url, ephemeral=True)

    @bot.tree.command(name="refresh", description="Read Home Assistant and save a fresh snapshot")
    async def refresh(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await poll_once(settings)
        except Exception as exc:
            await interaction.followup.send(f"Refresh failed: {exc}", ephemeral=True)
            return
        await interaction.followup.send(embed=_status_embed(settings), ephemeral=True)

    @bot.tree.command(name="trips", description="Show the five most recent detected trips")
    async def trips(interaction: discord.Interaction) -> None:
        with session_scope() as session:
            items = recent_trips(session, settings, limit=5)
        text = "No detected trips yet."
        if items:
            text = "\n".join(
                f"• {item['started_at']}: {item['distance_km']} km"
                for item in items
            )
        await interaction.response.send_message(text, ephemeral=True)

    @bot.tree.command(name="fuel", description="Log a fuel fill-up")
    @app_commands.describe(
        liters="Litres added",
        total_cost="Total price paid",
        odometer_km="Current odometer in kilometres",
    )
    async def fuel(
        interaction: discord.Interaction,
        liters: float,
        total_cost: float,
        odometer_km: float | None = None,
    ) -> None:
        if liters <= 0 or total_cost <= 0:
            await interaction.response.send_message(
                "Litres and total cost must be greater than zero.",
                ephemeral=True,
            )
            return
        with session_scope() as session:
            vehicle = primary_vehicle(session, settings)
            if vehicle is None:
                await interaction.response.send_message(
                    "Poll the vehicle once before logging fuel.",
                    ephemeral=True,
                )
                return
            fill = add_fuel_fill(
                session,
                vehicle,
                liters=liters,
                total_cost=total_cost,
                odometer_km=odometer_km,
            )
        await interaction.response.send_message(
            f"Logged {fill.liters:.1f} L for ${fill.total_cost:.2f}.",
            ephemeral=True,
        )

    bot.run(settings.discord_bot_token, log_handler=None)
