from __future__ import annotations

from typing import Awaitable, Callable

import discord

from cogs.games._shared._core import BaseGame

StartCallback = Callable[[discord.Interaction], Awaitable[None]]
SetupCallback = Callable[[discord.Interaction], Awaitable[None]]


class LobbyView(discord.ui.View):
    """Join / Leave / Setup / Start / Cancel. One row, so the lobby stays small."""

    def __init__(
        self,
        game: BaseGame,
        *,
        on_start: StartCallback,
        on_setup: SetupCallback | None = None,
        setup_label: str = "Setup",
        timeout: int = 900,
    ) -> None:
        super().__init__(timeout=timeout)
        self.game = game
        self._on_start = on_start
        self._on_setup = on_setup

        if on_setup is None:
            self.remove_item(self.setup_btn)
        else:
            self.setup_btn.label = setup_label

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content=self.game.lobby_text(), view=self)

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success, emoji="✅")
    async def join_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        error = self.game.add_player(interaction.user)
        if error:
            return await interaction.response.send_message(error, ephemeral=True)
        await self.refresh(interaction)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, emoji="🚪")
    async def leave_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        error = self.game.remove_player(interaction.user)
        if error:
            return await interaction.response.send_message(error, ephemeral=True)
        await self.refresh(interaction)

    @discord.ui.button(label="Setup", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def setup_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.game.is_host(interaction.user):
            return await interaction.response.send_message(
                "Only the host can change settings.", ephemeral=True
            )
        assert self._on_setup is not None
        await self._on_setup(interaction)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary, emoji="▶️")
    async def start_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.game.is_host(interaction.user):
            return await interaction.response.send_message(
                "Only the host can start the game.", ephemeral=True
            )
        if self.game.count < self.game.min_players:
            return await interaction.response.send_message(
                f"Need at least **{self.game.min_players}** players — there are {self.game.count}.",
                ephemeral=True,
            )
        await self._on_start(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="🛑")
    async def cancel_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.game.is_host(interaction.user):
            return await interaction.response.send_message(
                "Only the host can cancel.", ephemeral=True
            )
        await self.game.finish()
        self.stop()
        await interaction.response.edit_message(
            content=f"{self.game.emoji} **{self.game.name}** — cancelled by the host.", view=None
        )

    async def on_timeout(self) -> None:
        if not self.game.started:
            await self.game.finish()
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.game.message:
            try:
                await self.game.message.edit(view=self)
            except discord.HTTPException:
                pass
