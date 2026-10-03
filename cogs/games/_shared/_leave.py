"""
Leaving a game that has already started.

Quitting mid-game is not the same as leaving a lobby: a Mafia player still
holds a role the table needs to see, and a departing Psychic takes the round
with them. So the button only ever opens a confirmation, and each game decides
for itself what the departure actually does.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord

LeaveCallback = Callable[[discord.Interaction], Awaitable[None]]


class ConfirmLeave(discord.ui.View):
    """The are-you-sure, shown only to the player who tapped Leave."""

    def __init__(self, on_confirm: LeaveCallback) -> None:
        super().__init__(timeout=120)
        self._on_confirm = on_confirm

    @discord.ui.button(label="Yes, leave", style=discord.ButtonStyle.danger, emoji="\U0001F6AA")
    async def yes(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            content="You've left the game.", view=None
        )
        await self._on_confirm(interaction)

    @discord.ui.button(label="Stay in", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="Still in. 👍", view=None)

    async def on_timeout(self) -> None:
        # Silence beats leaving somebody out of a game they never confirmed.
        self.stop()


async def ask_to_leave(
    interaction: discord.Interaction,
    *,
    warning: str,
    on_confirm: LeaveCallback,
) -> None:
    """Open the confirmation. `warning` says what leaving costs in this game."""
    await interaction.response.send_message(
        f"**Leave the game?**\n{warning}\n-# You can't rejoin this one.",
        view=ConfirmLeave(on_confirm),
        ephemeral=True,
    )
