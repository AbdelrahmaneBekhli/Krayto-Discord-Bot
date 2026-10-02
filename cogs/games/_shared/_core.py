from __future__ import annotations

import discord

# One game per channel. Keyed by channel id.
_ACTIVE: dict[int, "BaseGame"] = {}


def active_game(channel_id: int) -> "BaseGame | None":
    return _ACTIVE.get(channel_id)


def register(game: "BaseGame") -> None:
    _ACTIVE[game.channel.id] = game


def unregister(channel_id: int) -> None:
    _ACTIVE.pop(channel_id, None)


class BaseGame:
    """Shared lobby bookkeeping. Subclasses own their own phases and views."""

    name = "Game"
    emoji = "🎮"
    min_players = 3
    max_players = 20

    def __init__(self, channel: discord.abc.MessageableChannel, host: discord.Member) -> None:
        self.channel = channel
        self.host = host
        # dict preserves join order, which keeps seat order stable
        self.players: dict[int, discord.Member] = {host.id: host}
        self.message: discord.Message | None = None
        self.started = False
        self.finished = False

    # -- players ---------------------------------------------------------

    @property
    def roster(self) -> list[discord.Member]:
        return list(self.players.values())

    @property
    def count(self) -> int:
        return len(self.players)

    def is_host(self, user: discord.abc.User) -> bool:
        return user.id == self.host.id

    def add_player(self, member: discord.Member) -> str | None:
        """Returns an error message, or None on success."""
        if member.id in self.players:
            return "You're already in."
        if self.count >= self.max_players:
            return f"The lobby is full ({self.max_players})."
        self.players[member.id] = member
        return None

    def remove_player(self, member: discord.abc.User) -> str | None:
        if member.id not in self.players:
            return "You're not in this game."
        if member.id == self.host.id:
            return "The host can't leave — cancel the game instead."
        del self.players[member.id]
        return None

    # -- lifecycle -------------------------------------------------------

    def lobby_text(self) -> str:
        """Compact lobby body. Subclasses usually append a settings line."""
        names = ", ".join(p.display_name for p in self.roster)
        need = max(0, self.min_players - self.count)
        status = f"need {need} more" if need else "ready"
        return (
            f"{self.emoji} **{self.name}** — hosted by {self.host.display_name}\n"
            f"**{self.count}** joined ({status}): {names}"
        )

    async def finish(self) -> None:
        self.finished = True
        unregister(self.channel.id)


def bar(position: int, slots: int = 10) -> str:
    """A tiny text gauge: ───●────── for position (1-indexed)."""
    position = max(1, min(slots, position))
    return "─" * (position - 1) + "●" + "─" * (slots - position)
