from __future__ import annotations

import logging
import os
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

log = logging.getLogger("bot")

BASE_DIR = Path(__file__).resolve().parent

EXTENSIONS = (
    "cogs.general",
    "cogs.help",
    "cogs.questions.tod",
    "cogs.questions.nhie_wyr",
    "cogs.questions.paranoia",
)


def _read_token_file(path: Path) -> str | None:
    """Read a token from a plain-text or KEY=VALUE file."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            if key.strip().upper() not in {"DISCORD_TOKEN", "TOKEN", "BOT_TOKEN"}:
                continue
            line = value.strip().strip("'\"")
        return line or None
    return None


def load_token() -> str:
    """
    Resolve the bot token from, in order:
      1. the DISCORD_TOKEN environment variable
      2. a .env file next to main.py (DISCORD_TOKEN=...)
      3. tokens.txt next to main.py
    """
    token = os.getenv("DISCORD_TOKEN")
    if token:
        return token.strip()

    for name in (".env", "tokens.txt"):
        token = _read_token_file(BASE_DIR / name)
        if token:
            return token

    raise RuntimeError(
        "DISCORD_TOKEN is missing. Set $env:DISCORD_TOKEN, or put "
        "DISCORD_TOKEN=... in .env, or the raw token in tokens.txt"
    )


class MyBot(commands.Bot):
    def __init__(self) -> None:
        # Slash commands only, so no message-content intent is needed.
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default())
        self.session: aiohttp.ClientSession | None = None

    async def setup_hook(self) -> None:
        # ONE shared HTTP session for all cogs
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"User-Agent": "DiscordBot (truthordarebot.xyz)"},
        )

        # Load cogs. A broken cog is logged instead of taking the whole bot down.
        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
            except Exception:
                log.exception("Failed to load extension %s", ext)
            else:
                log.info("Loaded extension %s", ext)

        # Sync slash commands (global)
        synced = await self.tree.sync()
        log.info("Synced %d global command(s)", len(synced))

    async def on_ready(self) -> None:
        log.info("Logged in as %s (id=%s)", self.user, self.user.id if self.user else "?")

    async def close(self) -> None:
        # Proper shutdown
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()


def main() -> None:
    discord.utils.setup_logging(level=logging.INFO)
    bot = MyBot()
    bot.run(load_token(), log_handler=None)


if __name__ == "__main__":
    main()
