import discord
from discord import app_commands
from discord.ext import commands

from cogs.questions._shared._base_prompt_view import BasePromptView
from cogs.questions._shared._config import API_API, RATING_CHOICES
from cogs.questions._shared._http import api_get

async def fetch_paranoia(bot, rating: str) -> dict:
    return await api_get(bot, API_API, "/paranoia", rating=rating)


def make_embed(text: str, rating: str):
    title = "Paranoia"
    if rating != "any":
        title += f" ({rating.upper()})"
    return discord.Embed(title=title, description=text)


class ParanoiaView(BasePromptView):
    async def _update(self, interaction: discord.Interaction):
        if not await self.guard(interaction):
            return

        await interaction.response.defer()

        data = await fetch_paranoia(self.bot, self.rating)
        text = data.get("question") or "No prompt found."
        embed = make_embed(text, self.rating)

        await self.update_message(interaction, embed=embed)

    @discord.ui.button(label="Another", style=discord.ButtonStyle.primary, emoji="🔁")
    async def another_btn(self, interaction: discord.Interaction, _):
        await self._update(interaction)


class Paranoia(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="paranoia", description="Paranoia questions")
    @app_commands.describe(lock="Lock buttons to the command author")
    @app_commands.choices(rating=RATING_CHOICES)
    async def paranoia(
        self,
        interaction: discord.Interaction,
        rating: app_commands.Choice[str] | None = None,
        lock: bool | None = None,
    ):
        selected_rating = rating.value if rating else "any"
        owner_id = interaction.user.id if lock is True else None

        data = await fetch_paranoia(self.bot, selected_rating)
        text = data.get("question") or "No prompt found."
        embed = make_embed(text, selected_rating)

        view = ParanoiaView(bot=self.bot, rating=selected_rating, owner_id=owner_id)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(Paranoia(bot))
