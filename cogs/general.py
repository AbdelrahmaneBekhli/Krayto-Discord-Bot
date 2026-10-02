from __future__ import annotations

import math
import time

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry


def _format_latency(seconds: float) -> str:
    """Render a latency in ms, or an em dash if it isn't a usable number."""
    if not math.isfinite(seconds):
        return "—"
    return f"{seconds * 1000:.0f}ms"


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
        # Time the actual REST round-trip: send first, then measure how long
        # Discord took to accept it.
        start = time.perf_counter()
        await interaction.response.send_message("Pinging…")
        api = time.perf_counter() - start

        # bot.latency is the gateway heartbeat RTT. It refreshes once per
        # heartbeat (~41s), so repeated pings inside one window read the same
        # number by design -- it is a cached measurement, not a fresh one.
        embed = discord.Embed(title="Pong! 🏓", colour=discord.Colour.green())
        embed.add_field(name="Gateway", value=_format_latency(self.bot.latency), inline=True)
        embed.add_field(name="API", value=_format_latency(api), inline=True)
        embed.set_footer(text="Gateway = heartbeat RTT (updates ~every 41s) · API = this request")

        await interaction.edit_original_response(content=None, embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
