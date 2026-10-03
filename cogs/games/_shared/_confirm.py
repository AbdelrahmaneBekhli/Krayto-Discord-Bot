"""
Are-you-sure, for the buttons that affect everybody.

Restarting or ending wipes a game other people are in the middle of, so the
host gets one tap to think again. The prompt is ephemeral: nobody else needs
to watch the host hesitate.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord

ConfirmCallback = Callable[[discord.Interaction], Awaitable[None]]


class Confirm(discord.ui.View):
    def __init__(self, on_confirm: ConfirmCallback, *, label: str, emoji: str) -> None:
        super().__init__(timeout=120)
        self._on_confirm = on_confirm
        self.yes.label = label
        self.yes.emoji = emoji

    @discord.ui.button(style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="On it…", view=None)
        await self._on_confirm(interaction)

    @discord.ui.button(label="Never mind", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="Left as it is.", view=None)

    async def on_timeout(self) -> None:
        # Doing nothing is the safe outcome for every button that lands here.
        self.stop()


async def ask(
    interaction: discord.Interaction,
    *,
    question: str,
    detail: str,
    label: str,
    emoji: str,
    on_confirm: ConfirmCallback,
) -> None:
    await interaction.response.send_message(
        f"**{question}**\n{detail}",
        view=Confirm(on_confirm, label=label, emoji=emoji),
        ephemeral=True,
    )
