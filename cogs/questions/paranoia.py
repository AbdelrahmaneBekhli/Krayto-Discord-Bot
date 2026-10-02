from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry
from cogs.questions._shared._base_prompt_view import BasePromptView
from cogs.questions._shared._config import API_API, RATING_CHOICES
from cogs.questions._shared._http import api_get, prompt_text


async def fetch_paranoia(bot, rating: str) -> dict:
    return await api_get(bot, API_API, "/paranoia", rating=rating)


def make_embed(text: str, rating: str) -> discord.Embed:
    title = "Paranoia"
    if rating != "any":
        title += f" ({rating.upper()})"
    return discord.Embed(title=title, description=text, colour=discord.Colour.purple())


class ParanoiaView(BasePromptView):
    @discord.ui.button(label="Another", style=discord.ButtonStyle.primary, emoji="🔁")
    async def another_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()

        data = await fetch_paranoia(self.bot, self.rating)
        await self.update_message(interaction, embed=make_embed(prompt_text(data), self.rating))


class Paranoia(commands.Cog):
    HELP_ENTRIES = [
        HelpEntry(
            name="paranoia",
            summary="Paranoia questions with an “Another” button",
            category="Games",
            examples=[
                "/paranoia",
                "/paranoia rating:PG",
                "/paranoia lock:true",
            ],
            show_in_help=True,
            options_help={
                "rating": "Filter question rating (Any/PG/PG-13/R)",
                "lock": "true = only you can press the button",
            },
        )
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="paranoia", description="Paranoia questions")
    @app_commands.describe(lock="Lock buttons to the command author")
    @app_commands.choices(rating=RATING_CHOICES)
    async def paranoia(
        self,
        interaction: discord.Interaction,
        rating: app_commands.Choice[str] | None = None,
        lock: bool = False,
    ) -> None:
        selected_rating = rating.value if rating else "any"
        owner_id = interaction.user.id if lock else None

        # Defer first: the API call below can outlast Discord's 3s reply window.
        await interaction.response.defer()

        data = await fetch_paranoia(self.bot, selected_rating)

        view = ParanoiaView(bot=self.bot, rating=selected_rating, owner_id=owner_id)
        view.message = await interaction.followup.send(
            embed=make_embed(prompt_text(data), selected_rating),
            view=view,
            wait=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Paranoia(bot))
