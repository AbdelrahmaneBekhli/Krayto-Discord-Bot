from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry
from cogs.questions._shared._base_prompt_view import BasePromptView
from cogs.questions._shared._config import API_API, RATING_CHOICES
from cogs.questions._shared._http import api_get, prompt_text

KINDS = ("nhie", "wyr")
TITLES = {"nhie": "Never Have I Ever", "wyr": "Would You Rather"}


async def fetch_prompt(bot, kind: str, rating: str) -> dict:
    # kind = "nhie" or "wyr"
    return await api_get(bot, API_API, f"/{kind}", rating=rating)


def make_embed(kind: str, text: str, rating: str) -> discord.Embed:
    title = TITLES.get(kind, kind.upper())
    if rating != "any":
        title += f" ({rating.upper()})"
    colour = discord.Colour.green() if kind == "nhie" else discord.Colour.blurple()
    return discord.Embed(title=title, description=text, colour=colour)


class NHIEWYRView(BasePromptView):
    async def _handle(self, interaction: discord.Interaction, kind: str) -> None:
        await interaction.response.defer()

        data = await fetch_prompt(self.bot, kind, self.rating)
        await self.update_message(
            interaction,
            embed=make_embed(kind, prompt_text(data), self.rating),
        )

    @discord.ui.button(label="NHIE", style=discord.ButtonStyle.success, emoji="🙋")
    async def nhie_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, "nhie")

    @discord.ui.button(label="WYR", style=discord.ButtonStyle.primary, emoji="🤔")
    async def wyr_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, "wyr")

    @discord.ui.button(label="Random", style=discord.ButtonStyle.secondary, emoji="🎲")
    async def random_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._handle(interaction, random.choice(KINDS))


class NHIEWYR(commands.Cog):
    HELP_ENTRIES = [
        HelpEntry(
            name="nhie_wyr",
            summary="Never Have I Ever & Would You Rather buttons",
            category="Games",
            examples=[
                "/nhie_wyr",
                "/nhie_wyr rating:Any",
                "/nhie_wyr rating:PG lock:true",
            ],
            show_in_help=True,
            options_help={
                "rating": "Choose the content rating: Any, PG, PG-13, R",
                "lock": "Lock buttons so only you can press them (true/false)",
            },
        )
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="nhie_wyr", description="Never Have I Ever / Would You Rather")
    @app_commands.describe(lock="Lock buttons to the command author")
    @app_commands.choices(rating=RATING_CHOICES)
    async def nhie_wyr(
        self,
        interaction: discord.Interaction,
        rating: app_commands.Choice[str] | None = None,
        lock: bool = False,
    ) -> None:
        selected_rating = rating.value if rating else "any"
        owner_id = interaction.user.id if lock else None

        # Defer first: the API call below can outlast Discord's 3s reply window.
        await interaction.response.defer()

        first_kind = random.choice(KINDS)
        data = await fetch_prompt(self.bot, first_kind, selected_rating)

        view = NHIEWYRView(bot=self.bot, rating=selected_rating, owner_id=owner_id)
        view.message = await interaction.followup.send(
            embed=make_embed(first_kind, prompt_text(data), selected_rating),
            view=view,
            wait=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NHIEWYR(bot))
