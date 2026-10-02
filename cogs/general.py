from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry


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
        # bot.latency is nan until the first heartbeat completes.
        latency = self.bot.latency
        if latency != latency or latency in (float("inf"), float("-inf")):
            suffix = ""
        else:
            suffix = f" ({latency * 1000:.0f}ms)"
        await interaction.response.send_message(f"Pong! 🏓{suffix}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
