import random, discord
from discord import app_commands
from discord.ext import commands

from cogs.questions._shared._base_prompt_view import BasePromptView
from cogs.questions._shared._config import API_API, RATING_CHOICES
from cogs.questions._shared._http import api_get
from cogs._help_registry import HelpEntry

async def fetch_tod(bot, kind: str, rating: str) -> dict:
    # kind = "truth" or "dare"
    return await api_get(bot, API_API, f"/{kind}", rating=rating)

def make_embed(kind: str, text: str, rating: str):
    title = kind.capitalize() + (f" ({rating.upper()})" if rating != "any" else "")
    return discord.Embed(title=title, description=text)

class TODView(BasePromptView):
    async def _handle(self, interaction: discord.Interaction, kind: str):
        if not await self.guard(interaction):
            return
        await interaction.response.defer()

        data = await fetch_tod(self.bot, kind, self.rating)
        text = data.get("question") or data.get("dare") or "No prompt found."
        await self.update_message(interaction, embed=make_embed(kind, text, self.rating))

    # Buttons
    @discord.ui.button(label="Truth", style=discord.ButtonStyle.success, emoji="✅")
    async def truth_btn(self, interaction: discord.Interaction, _):
        await self._handle(interaction, "truth")

    @discord.ui.button(label="Dare", style=discord.ButtonStyle.danger, emoji="🔥")
    async def dare_btn(self, interaction: discord.Interaction, _):
        await self._handle(interaction, "dare")

    @discord.ui.button(label="Random", style=discord.ButtonStyle.primary, emoji="🎲")
    async def random_btn(self, interaction: discord.Interaction, _):
        await self._handle(interaction, random.choice(["truth", "dare"]))

    # Command
class TOD(commands.Cog):
    HELP_ENTRIES = [
        HelpEntry(
            name="tod",
            summary="Truth / Dare / Random buttons",
            category="Games",
            examples=["/tod", "/tod rating:PG lock:true"],
            show_in_help=True,
            options_help={
                "rating": "Choose the content rating: Any, PG, PG-13, R",
                "lock": "Lock buttons so only you can press them (true/false)"
            }
        )
    ]
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tod", description="Truth or Dare")
    @app_commands.describe(lock="Lock buttons to the command author")
    @app_commands.choices(rating=RATING_CHOICES)
    async def tod(self, interaction: discord.Interaction,
                  rating: app_commands.Choice[str] | None = None,
                  lock: bool | None = None):
        selected_rating = rating.value if rating else "any"
        owner_id = interaction.user.id if lock is True else None

        first_kind = random.choice(["truth", "dare"])
        data = await fetch_tod(self.bot, first_kind, selected_rating)
        text = data.get("question") or data.get("dare") or "No prompt found."

        view = TODView(bot=self.bot, rating=selected_rating, owner_id=owner_id)
        await interaction.response.send_message(embed=make_embed(first_kind, text, selected_rating), view=view)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(TOD(bot))
