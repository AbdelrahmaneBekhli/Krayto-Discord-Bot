import os
import aiohttp
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Put it in .env or set $env:DISCORD_TOKEN")

intents = discord.Intents.default()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)  # prefix unused
        self.session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        # ONE shared HTTP session for all cogs
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"User-Agent": "DiscordBot (truthordarebot.xyz)"},
        )

        # Load cogs
        await self.load_extension("cogs.general")
        await self.load_extension("cogs.questions.tod")
        await self.load_extension("cogs.questions.nhie_wyr")
        await self.load_extension("cogs.questions.paranoia")

        # Sync slash commands (global)
        await self.tree.sync()

    async def on_ready(self):
        print(f"✅ Logged in as {self.user}")

    async def close(self):
        # Proper shutdown
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()

bot = MyBot()
bot.run(TOKEN)
