import discord
from discord.ext import commands

class BasePromptView(discord.ui.View):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        rating: str,
        owner_id: int | None,
        timeout: int = 180
    ):
        super().__init__(timeout=timeout)
        self.bot = bot                      # shared bot reference (for shared HTTP session)
        self.rating = rating or "any"
        self.owner_id = owner_id            # None = unlocked
        self.message: discord.Message | None = None

    async def guard(self, interaction: discord.Interaction) -> bool:
        if self.owner_id is not None and interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "🔒 This session is locked to the command author.",
                ephemeral=True
            )
            return False
        return True

    async def update_message(self, interaction: discord.Interaction, *, embed: discord.Embed):
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
