from __future__ import annotations

import logging

import discord
from discord.ext import commands

log = logging.getLogger(__name__)


class BasePromptView(discord.ui.View):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        rating: str,
        owner_id: int | None,
        timeout: int = 180,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot                      # shared bot reference (for shared HTTP session)
        self.rating = rating or "any"
        self.owner_id = owner_id            # None = unlocked
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Runs before every child component, so each button is covered."""
        if self.owner_id is None or interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            "🔒 This session is locked to the command author.",
            ephemeral=True,
        )
        return False

    async def update_message(self, interaction: discord.Interaction, *, embed: discord.Embed) -> None:
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ) -> None:
        log.exception("Error in %s component %r", type(self).__name__, item, exc_info=error)

        message = "⚠️ Something went wrong. Please try again."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

        self.stop()
