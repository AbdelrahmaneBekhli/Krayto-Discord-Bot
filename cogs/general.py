from __future__ import annotations

import math
import time

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry

# Rough feel thresholds in milliseconds.
_BANDS = ((150.0, "🟢"), (300.0, "🟡"), (math.inf, "🔴"))


def _dot(ms: float) -> str:
    """Green/amber/red dot for a latency, so health reads at a glance."""
    for limit, emoji in _BANDS:
        if ms < limit:
            return emoji
    return _BANDS[-1][1]


class General(commands.Cog):
    # Help metadata for this cog
    HELP_ENTRIES = [
        HelpEntry(
            name="ping",
            summary="Check if the bot is online and responsive",
            category="Utility",
            examples=["/ping"],
            show_in_help=True,
        )
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping(self, interaction: discord.Interaction) -> None:
        # Time the real round-trip: send first, then measure how long Discord
        # took to accept it.
        start = time.perf_counter()
        await interaction.response.send_message("Pinging…")
        reply_ms = (time.perf_counter() - start) * 1000

        # bot.latency is the gateway heartbeat round-trip, cached and only
        # refreshed every ~41s, and nan until the first heartbeat lands.
        latency = self.bot.latency
        if math.isfinite(latency):
            gateway_ms = latency * 1000
            connection = f"{_dot(gateway_ms)} connection **{gateway_ms:.0f}ms**"
        else:
            connection = "⚪ connection **starting up**"

        await interaction.edit_original_response(
            content=f"Pong! 🏓  {connection}  ·  {_dot(reply_ms)} reply **{reply_ms:.0f}ms**"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
