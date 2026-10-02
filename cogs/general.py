from __future__ import annotations

import math
import time

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry

# Rough feel thresholds in milliseconds, worst-first when picking a verdict.
_BANDS = (
    (150.0, "🟢", "great", discord.Colour.green()),
    (300.0, "🟡", "okay", discord.Colour.gold()),
    (math.inf, "🔴", "a bit slow", discord.Colour.red()),
)


def _band(ms: float):
    """Pick the (emoji, word, colour) band a latency falls into."""
    for limit, emoji, word, colour in _BANDS:
        if ms < limit:
            return emoji, word, colour
    return _BANDS[-1][1:]


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

        # bot.latency is the gateway heartbeat round-trip. It refreshes once
        # per heartbeat (~41s), so repeated pings in one window read the same
        # cached number by design.
        gateway = self.bot.latency * 1000 if math.isfinite(self.bot.latency) else None

        reply_emoji, reply_word, reply_colour = _band(reply_ms)
        if gateway is None:
            conn_emoji, conn_value = "⚪", "starting up…"
            verdict, colour = reply_word, reply_colour
            worst = reply_ms
        else:
            conn_emoji, _, _ = _band(gateway)
            conn_value = f"**{gateway:.0f}ms**"
            worst = max(gateway, reply_ms)
            _, verdict, colour = _band(worst)

        embed = discord.Embed(
            title="Pong! 🏓",
            description=f"I'm online and things are looking **{verdict}**.",
            colour=colour,
        )
        embed.add_field(
            name=f"{conn_emoji} Connection",
            value=f"{conn_value}\nMy link to Discord",
            inline=True,
        )
        embed.add_field(
            name=f"{reply_emoji} Reply speed",
            value=f"**{reply_ms:.0f}ms**\nHow long this reply took",
            inline=True,
        )
        embed.set_footer(text="Connection is only checked every ~40s, so it changes slowly.")

        await interaction.edit_original_response(content=None, embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
