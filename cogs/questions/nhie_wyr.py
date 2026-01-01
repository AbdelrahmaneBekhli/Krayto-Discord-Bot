import random, discord
from discord import app_commands
from discord.ext import commands

from cogs.questions._shared._base_prompt_view import BasePromptView
from cogs.questions._shared._config import API_API, RATING_CHOICES
from cogs.questions._shared._http import api_get

async def fetch_prompt(bot, kind: str, rating: str) -> dict:
    # kind = "nhie" or "wyr"
    return await api_get(bot, API_API, f"/{kind}", rating=rating)

def make_embed(kind: str, text: str, rating: str):
    title = ("Never Have I Ever" if kind == "nhie" else "Would You Rather")
    if rating != "any":
        title += f" ({rating.upper()})"
    return discord.Embed(title=title, description=text)

class NHIEWYRView(BasePromptView):
    async def _handle(self, interaction: discord.Interaction, kind: str):
        if not await self.guard(interaction):
            return

        await interaction.response.defer()

        data = await fetch_prompt(self.bot, kind, self.rating)
        text = data.get("question") or "No prompt found."

        await self.update_message(
            interaction,
            embed=make_embed(kind, text, self.rating)
        )

    # Buttons
    @discord.ui.button(label="NHIE", style=discord.ButtonStyle.success, emoji="🙋")
    async def nhie_btn(self, interaction: discord.Interaction, _):
        await self._handle(interaction, "nhie")

    @discord.ui.button(label="WYR", style=discord.ButtonStyle.primary, emoji="🤔")
    async def wyr_btn(self, interaction: discord.Interaction, _):
        await self._handle(interaction, "wyr")

    @discord.ui.button(label="Random", style=discord.ButtonStyle.secondary, emoji="🎲")
    async def random_btn(self, interaction: discord.Interaction, _):
        await self._handle(interaction, random.choice(["nhie", "wyr"]))

    # Command
class NHIEWYR(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="nhie_wyr", description="Never Have I Ever / Would You Rather")
    @app_commands.describe(lock="Lock buttons to the command author")
    @app_commands.choices(rating=RATING_CHOICES)
    async def nhie_wyr(self, interaction: discord.Interaction, rating: app_commands.Choice[str] | None = None, lock: bool | None = None):
        selected_rating = rating.value if rating else "any"
        owner_id = interaction.user.id if lock is True else None

        first_kind = random.choice(["nhie", "wyr"])
        data = await fetch_prompt(self.bot, first_kind, selected_rating)
        text = data.get("question") or "No prompt found."

        view = NHIEWYRView(bot=self.bot, rating=selected_rating, owner_id=owner_id)
        await interaction.response.send_message(embed=make_embed(first_kind, text, selected_rating), view=view)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(NHIEWYR(bot))
