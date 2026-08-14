from __future__ import annotations

"""Discord commands for the account owner's locally stored vehicle data."""

import discord
from discord import app_commands

from .analytics import recent_trips, status_summary
from .config import Settings
from .db import init_db, session_scope
from .insights import (
    add_maintenance_record,
    add_named_location_from_current,
    current_vehicle_location,
    fuel_analytics,
    maintenance_history,
    named_locations,
    vehicle_timeline,
    weekly_summary,
)
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

    @bot.tree.command(name="where", description="Show the latest saved Lexus parking location")
    async def where(interaction: discord.Interaction) -> None:
        with session_scope() as session:
            location = current_vehicle_location(session, settings)
        if not location.get("ready"):
            text = "No saved vehicle location yet."
        else:
            text = (
                f"📍 **{location.get('label', 'Unknown location')}**\n"
                f"Fuel: {_fmt(location.get('fuel_percent'), '%')} · "
                f"Range: {_fmt(location.get('range_km'), ' km')}\n"
                f"Last saved: {location.get('observed_at') or '—'}"
            )
            if location.get("parked_since"):
                text += f"\nParked since: {location['parked_since']}"
            if settings.dashboard_url:
                text += f"\n{settings.dashboard_url}"
        await interaction.response.send_message(text, ephemeral=True)

    @bot.tree.command(name="locations", description="List saved named Lexus locations")
    async def locations(interaction: discord.Interaction) -> None:
        with session_scope() as session:
            items = named_locations(session, settings)
        if not items:
            text = "No named locations yet. Use `/location_add` while the Lexus is there."
        else:
            text = "\n".join(
                f"• **{item['name']}** · {item['radius_m']} m"
                + (" · private" if item["is_private"] else "")
                for item in items
            )
        await interaction.response.send_message(text, ephemeral=True)

    @bot.tree.command(name="location_add", description="Name the Lexus's current saved location")
    @app_commands.describe(
        name="Location name, for example Home or Work",
        radius_m="Geofence radius in metres",
        is_private="Hide the location name in notifications",
    )
    async def location_add(
        interaction: discord.Interaction,
        name: str,
        radius_m: float | None = None,
        is_private: bool = False,
    ) -> None:
        if radius_m is not None and not 25 <= radius_m <= 5000:
            await interaction.response.send_message(
                "Radius must be between 25 and 5000 metres.",
                ephemeral=True,
            )
            return
        try:
            with session_scope() as session:
                location = add_named_location_from_current(
                    session,
                    settings,
                    name=name,
                    radius_m=radius_m,
                    is_private=is_private,
                )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Saved **{location.name}** with a {location.radius_m:.0f} m radius"
            + (" as a private zone." if location.is_private else "."),
            ephemeral=True,
        )

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
                f"• **{item['start_label']} → {item['end_label']}** · "
                f"{item['distance_km']} km · {item['started_at']}"
                for item in items
            )
        await interaction.response.send_message(text, ephemeral=True)

    @bot.tree.command(name="timeline", description="Show recent Lexus activity")
    async def timeline(interaction: discord.Interaction) -> None:
        with session_scope() as session:
            items = vehicle_timeline(session, settings, limit=12)
        text = "No vehicle activity yet."
        if items:
            text = "\n".join(f"• {item['at']} · {item['text']}" for item in items)
        await interaction.response.send_message(text[:1900], ephemeral=True)

    @bot.tree.command(name="fuelstats", description="Show fuel economy and spending analytics")
    async def fuelstats(interaction: discord.Interaction) -> None:
        with session_scope() as session:
            stats = fuel_analytics(session, settings)
        if not stats.get("ready"):
            text = "No fuel data yet."
        else:
            economy = stats.get("average_l_per_100km")
            cost_per_km = stats.get("average_cost_per_km")
            text = (
                f"⛽ **Fuel analytics**\n"
                f"30-day spend: ${stats['spend_30d']:.2f} · {stats['liters_30d']} L\n"
                f"Average economy: {economy if economy is not None else '—'} L/100 km\n"
                f"Average cost: ${cost_per_km if cost_per_km is not None else '—'} / km\n"
                f"Logged fill-ups: {stats['fill_count']}"
            )
        await interaction.response.send_message(text, ephemeral=True)

    @bot.tree.command(name="fuel", description="Log a fuel fill-up")
    @app_commands.describe(
        liters="Litres added",
        total_cost="Total price paid",
        odometer_km="Current odometer in kilometres; omit to use the latest Lexus reading",
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
            f"Logged {fill.liters:.1f} L for ${fill.total_cost:.2f} at "
            f"{_fmt(fill.odometer_km, ' km')}.",
            ephemeral=True,
        )

    @bot.tree.command(name="maintenance", description="Show recent Lexus maintenance history")
    async def maintenance(interaction: discord.Interaction) -> None:
        with session_scope() as session:
            items = maintenance_history(session, settings, limit=8)
        if not items:
            text = "No maintenance records yet."
        else:
            text = "\n".join(
                f"• **{item['kind']}** · {item['performed_at']} · "
                f"{_fmt(item['odometer_km'], ' km')}"
                for item in items
            )
        await interaction.response.send_message(text, ephemeral=True)

    @bot.tree.command(name="maintenance_add", description="Log a Lexus maintenance event")
    @app_commands.describe(
        kind="Oil change, tire rotation, brakes, detailing, etc.",
        cost="Optional total cost",
        next_due_km="Optional odometer when this service is next due",
        notes="Optional notes",
    )
    async def maintenance_add(
        interaction: discord.Interaction,
        kind: str,
        cost: float | None = None,
        next_due_km: float | None = None,
        notes: str | None = None,
    ) -> None:
        if cost is not None and cost < 0:
            await interaction.response.send_message("Cost cannot be negative.", ephemeral=True)
            return
        try:
            with session_scope() as session:
                record = add_maintenance_record(
                    session,
                    settings,
                    kind=kind,
                    cost=cost,
                    notes=notes,
                    next_due_km=next_due_km,
                )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Logged **{record.kind}** at {_fmt(record.odometer_km, ' km')}.",
            ephemeral=True,
        )

    @bot.tree.command(name="weekly", description="Show the current seven-day driving summary")
    async def weekly(interaction: discord.Interaction) -> None:
        with session_scope() as session:
            summary = weekly_summary(session, settings)
        if not summary.get("ready"):
            text = "No saved vehicle data yet."
        else:
            text = (
                f"📊 **7-day driving summary**\n"
                f"Distance: {summary['distance_km']} km · Trips: {summary['trip_count']}\n"
                f"Average trip: {summary['average_trip_km']} km · "
                f"Longest: {summary['longest_trip_km']} km\n"
                f"Fuel spend: ${summary['fuel_spend']:.2f} · {summary['fuel_liters']} L"
            )
        await interaction.response.send_message(text, ephemeral=True)

    bot.run(settings.discord_bot_token, log_handler=None)
