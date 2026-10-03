from __future__ import annotations

import discord


class Palette:
    """Phase colours. The colour is the fastest signal of what's happening."""

    LOBBY = discord.Colour.blurple()
    WARN = discord.Colour.orange()
    NIGHT = discord.Colour.from_rgb(43, 45, 102)
    DAY = discord.Colour.gold()
    VOTE = discord.Colour.orange()
    TOWN_WIN = discord.Colour.green()
    MAFIA_WIN = discord.Colour.from_rgb(190, 40, 40)
    ROUND = discord.Colour.teal()
    REVEAL = discord.Colour.purple()
    OVER = discord.Colour.dark_grey()


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

    def drop_player(self, member: discord.abc.User) -> bool:
        """
        Remove someone from a game already in progress.

        Unlike `remove_player` the host may go: once play has started there is
        nothing to cancel back to, so the host badge moves to whoever is next
        rather than trapping them in a game they want to leave.
        """
        if member.id not in self.players:
            return False
        del self.players[member.id]
        if member.id == self.host.id and self.players:
            self.host = next(iter(self.players.values()))
        return True

    # -- lifecycle -------------------------------------------------------

    def lobby_embed(self) -> discord.Embed:
        """Compact lobby card. Subclasses add at most one more field."""
        need = max(0, self.min_players - self.count)
        status = f"need {need} more" if need else "ready to start"
        embed = discord.Embed(title=f"{self.emoji} {self.name}", colour=Palette.LOBBY)
        embed.add_field(
            name=f"Players ({self.count}) — {status}",
            value=", ".join(p.display_name for p in self.roster) or "nobody yet",
            inline=False,
        )
        embed.set_footer(text=f"Hosted by {self.host.display_name}")
        return embed

    async def finish(self) -> None:
        self.finished = True
        unregister(self.channel.id)


def bar(position: int, slots: int = 10) -> str:
    """A tiny text gauge: ───●────── for position (1-indexed)."""
    position = max(1, min(slots, position))
    return "─" * (position - 1) + "●" + "─" * (slots - position)
