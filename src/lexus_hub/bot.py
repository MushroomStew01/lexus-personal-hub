from __future__ import annotations

"""Discord commands for the account owner's locally stored vehicle data."""

import discord
from discord import app_commands

from .analytics import recent_trips, status_summary
from .config import Settings
from .db import init_db, session_scope
from .storage import add_fuel_fill, primary_vehicle


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


def _status_text(settings: Settings) -> str:
    with session_scope() as session:
        status = status_summary(session, settings)
    if not status.get("ready"):
        return "No saved vehicle data yet."
    return (
        f"**{settings.vehicle_display_name}**\n"
        f"Odometer: {status.get('odometer_km') or '—'} km\n"
        f"Fuel: {status.get('fuel_percent') or '—'}%\n"
        f"Range: {status.get('range_km') or '—'} km\n"
        f"Last 7 days: {status.get('distance_7d_km') or 0} km"
    )


def run_bot(settings: Settings) -> None:
    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required for `lexus-hub bot`.")
    init_db()
    bot = LexusBot(settings)

    @bot.tree.command(name="car", description="Show the latest saved vehicle status")
    async def car(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(_status_text(settings), ephemeral=True)

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
