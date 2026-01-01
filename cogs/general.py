import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry  # <-- add this import


class General(commands.Cog):
    # Help metadata for this cog
    HELP_ENTRIES = [
        HelpEntry(
            name="ping",
            summary="Check if the bot is online and responsive",
            category="Utility",
            examples=["/ping"],
            show_in_help=True
        )
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ping command
    @app_commands.command(name="ping", description="Check if the bot is alive")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong! 🏓")


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
