from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry
from cogs.games._shared._core import BaseGame, active_game, bar, register
from cogs.games._shared._lobby import LobbyView

SLOTS = 10

# Left pole, right pole.
SPECTRUMS = [
    ("Cold", "Hot"), ("Underrated", "Overrated"), ("Cheap", "Expensive"),
    ("Scary", "Comforting"), ("Boring", "Exciting"), ("Useless", "Essential"),
    ("Casual", "Formal"), ("Guilty pleasure", "Respected classic"),
    ("Forgettable", "Iconic"), ("Hard to learn", "Easy to learn"),
    ("Quiet", "Loud"), ("Ugly", "Beautiful"), ("A chore", "A treat"),
    ("Childish", "Grown-up"), ("Normal", "Weird"), ("Dangerous", "Safe"),
    ("Bad habit", "Good habit"), ("Polite", "Rude"), ("Smells bad", "Smells good"),
    ("Waste of money", "Worth every penny"), ("Common", "Rare"),
    ("Hated by everyone", "Loved by everyone"), ("Simple", "Complicated"),
    ("Fictional", "Real"), ("Bad advice", "Good advice"), ("Ordinary", "Legendary"),
    ("Fast", "Slow"), ("Round", "Pointy"), ("Dry", "Wet"),
    ("Would not survive a week", "Would thrive"),
    ("Terrible superpower", "Amazing superpower"), ("Embarrassing", "Impressive"),
    ("Overused", "Fresh"), ("Light", "Heavy"), ("Bad gift", "Great gift"),
    ("Avoid at all costs", "Highly recommend"), ("Messy", "Tidy"),
    ("Serious", "Silly"), ("Old-fashioned", "Modern"), ("Mild", "Spicy"),
    ("Temporary", "Forever"), ("Hard to explain", "Obvious"),
    ("Overpriced snack", "Great value snack"), ("Lazy", "Hard-working"),
    ("Bad idea at 3am", "Good idea at 3am"),
]


def gauge(position: int) -> str:
    return f"`{bar(position, SLOTS)}`"


def spectrum_line(left: str, right: str) -> str:
    return f"**{left}** |---------| **{right}**"


def score_for(guess: int, target: int) -> int:
    """Closer is better: exact band 4, one off 2, two off 1, else nothing."""
    return {0: 4, 1: 2, 2: 1}.get(abs(guess - target), 0)


class WavelengthGame(BaseGame):
    name = "Wavelength"
    emoji = "\U0001F4E1"  # satellite antenna
    min_players = 3
    max_players = 20

    def __init__(self, channel, host) -> None:
        super().__init__(channel, host)
        self.scores: dict[int, int] = {}
        self.order: list[int] = []
        self.round_index = -1
        self.left = ""
        self.right = ""
        self.target = 0
        self.clue: str | None = None
        self.guesses: dict[int, int] = {}
        self.unused = SPECTRUMS.copy()

    @property
    def psychic(self) -> discord.Member | None:
        if not self.order:
            return None
        return self.players.get(self.order[self.round_index % len(self.order)])

    @property
    def guessers(self) -> list[discord.Member]:
        psychic = self.psychic
        return [p for p in self.roster if psychic is None or p.id != psychic.id]

    def begin(self) -> None:
        self.started = True
        self.order = list(self.players)
        random.shuffle(self.order)
        self.scores = {pid: 0 for pid in self.players}

    def next_round(self) -> bool:
        """Set up the next round. False once everyone has been Psychic once."""
        self.round_index += 1
        if self.round_index >= len(self.order):
            return False
        if not self.unused:
            self.unused = SPECTRUMS.copy()
        self.left, self.right = self.unused.pop(random.randrange(len(self.unused)))
        self.target = random.randint(1, SLOTS)
        self.clue = None
        self.guesses = {}
        return True

    def scoreboard(self) -> str:
        ranked = sorted(self.scores.items(), key=lambda kv: kv[1], reverse=True)
        medals = ["\U0001F947", "\U0001F948", "\U0001F949"]
        parts = []
        for i, (pid, score) in enumerate(ranked):
            member = self.players.get(pid)
            if member is None:
                continue
            tag = medals[i] if i < len(medals) else "•"
            parts.append(f"{tag} {member.display_name} **{score}**")
        return " · ".join(parts)

    def lobby_text(self) -> str:
        return (
            f"{super().lobby_text()}\n"
            "-# One player gets a secret spot on a scale and gives a one-word clue. "
            "Everyone else guesses where it was."
        )


class ClueModal(discord.ui.Modal, title="Your clue"):
    clue = discord.ui.TextInput(
        label="One word or short phrase",
        placeholder="something that sits exactly on your secret spot",
        max_length=80,
    )

    def __init__(self, round_view: "RoundView") -> None:
        super().__init__()
        self.round_view = round_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.round_view.game.clue = str(self.clue).strip()
        await self.round_view.show_guessing(interaction)


class GuessSelect(discord.ui.Select):
    def __init__(self, round_view: "RoundView") -> None:
        options = [
            discord.SelectOption(label=str(i), description=bar(i, SLOTS), value=str(i))
            for i in range(1, SLOTS + 1)
        ]
        super().__init__(placeholder="Where on the scale?", options=options)
        self.round_view = round_view

    async def callback(self, interaction: discord.Interaction) -> None:
        guess = int(self.values[0])
        self.round_view.game.guesses[interaction.user.id] = guess
        await interaction.response.edit_message(
            content=f"Locked in: {gauge(guess)}  You can change it until the reveal.",
            view=None,
        )
        await self.round_view.refresh_public()


class GuessPrompt(discord.ui.View):
    """Ephemeral, one per guesser."""

    def __init__(self, round_view: "RoundView") -> None:
        super().__init__(timeout=600)
        self.add_item(GuessSelect(round_view))


class RoundView(discord.ui.View):
    def __init__(self, game: WavelengthGame) -> None:
        super().__init__(timeout=1800)
        self.game = game
        # Only the Psychic button shows first; the others are added after the clue.
        self.remove_item(self.guess_btn)
        self.remove_item(self.reveal_btn)

    # -- rendering -------------------------------------------------------

    def clue_text(self) -> str:
        g = self.game
        psychic = g.psychic.display_name if g.psychic else "?"
        return (
            f"\U0001F4E1 **Round {g.round_index + 1}/{len(g.order)}** — "
            f"{psychic} is the Psychic\n"
            f"{spectrum_line(g.left, g.right)}\n"
            "-# Waiting for a clue..."
        )

    def guessing_text(self) -> str:
        g = self.game
        remaining = len(g.guessers) - len(g.guesses)
        tail = "" if remaining else " — everyone's in, reveal when ready"
        psychic = g.psychic.display_name if g.psychic else "?"
        return (
            f"\U0001F4E1 **Round {g.round_index + 1}/{len(g.order)}** — "
            f"{psychic} says: **“{g.clue}”**\n"
            f"{spectrum_line(g.left, g.right)}\n"
            f"-# {len(g.guesses)}/{len(g.guessers)} guessed{tail}"
        )

    async def refresh_public(self) -> None:
        if self.game.message:
            try:
                await self.game.message.edit(content=self.guessing_text(), view=self)
            except discord.HTTPException:
                pass

    async def show_guessing(self, interaction: discord.Interaction) -> None:
        self.clear_items()
        self.add_item(self.guess_btn)
        self.add_item(self.reveal_btn)
        await interaction.response.edit_message(content=self.guessing_text(), view=self)

    # -- buttons ---------------------------------------------------------

    @discord.ui.button(
        label="See my spot & give a clue", style=discord.ButtonStyle.primary, emoji="\U0001F52E"
    )
    async def psychic_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        g = self.game
        if g.psychic is None or interaction.user.id != g.psychic.id:
            return await interaction.response.send_message(
                "Only the Psychic for this round can do that.", ephemeral=True
            )
        if g.clue is not None:
            return await interaction.response.send_message(
                "You already gave your clue.", ephemeral=True
            )
        await interaction.response.send_message(
            f"{spectrum_line(g.left, g.right)}\n"
            f"Your secret spot: {gauge(g.target)} (**{g.target}**)\n"
            "-# Give a clue that sits exactly there. No numbers, no pointing.",
            ephemeral=True,
        )
        await interaction.followup.send(
            "Ready?", view=_ClueLauncher(self), ephemeral=True
        )

    @discord.ui.button(label="Guess", style=discord.ButtonStyle.success, emoji="\U0001F3AF")
    async def guess_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        g = self.game
        if interaction.user.id not in g.players:
            return await interaction.response.send_message(
                "You're not in this game.", ephemeral=True
            )
        if g.psychic and interaction.user.id == g.psychic.id:
            return await interaction.response.send_message(
                "You're the Psychic — you already know!", ephemeral=True
            )
        await interaction.response.send_message(
            f"{spectrum_line(g.left, g.right)}\nClue: **“{g.clue}”**",
            view=GuessPrompt(self),
            ephemeral=True,
        )

    @discord.ui.button(label="Reveal", style=discord.ButtonStyle.danger, emoji="\U0001F440")
    async def reveal_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        g = self.game
        allowed = g.is_host(interaction.user) or (g.psychic and interaction.user.id == g.psychic.id)
        if not allowed:
            return await interaction.response.send_message(
                "Only the host or the Psychic can reveal.", ephemeral=True
            )
        if not g.guesses:
            return await interaction.response.send_message(
                "Nobody has guessed yet.", ephemeral=True
            )
        self.stop()
        await interaction.response.edit_message(content=self.reveal_text(), view=None)
        await advance(g, interaction)

    def reveal_text(self) -> str:
        g = self.game
        lines = [
            f"\U0001F4E1 **Round {g.round_index + 1}** — the spot was "
            f"{gauge(g.target)} (**{g.target}**)",
            f"{spectrum_line(g.left, g.right)} · clue: **“{g.clue}”**",
            "",
        ]
        for member in g.guessers:
            guess = g.guesses.get(member.id)
            if guess is None:
                lines.append(f"• {member.display_name} — didn't guess")
                continue
            points = score_for(guess, g.target)
            g.scores[member.id] = g.scores.get(member.id, 0) + points
            mark = "\U0001F3AF" if points == 4 else ("✨" if points else "•")
            lines.append(f"{mark} {member.display_name} {gauge(guess)} **+{points}**")

        # The Psychic scores the average of their guessers, so a good clue pays.
        scored = [score_for(v, g.target) for v in g.guesses.values()]
        bonus = round(sum(scored) / len(scored)) if scored else 0
        if g.psychic:
            g.scores[g.psychic.id] = g.scores.get(g.psychic.id, 0) + bonus
            lines.append(f"\U0001F52E {g.psychic.display_name} (Psychic) **+{bonus}**")
        lines.append("")
        lines.append(g.scoreboard())
        return "\n".join(lines)


class _ClueLauncher(discord.ui.View):
    """A modal can only open from a fresh interaction, so this gives us one."""

    def __init__(self, round_view: RoundView) -> None:
        super().__init__(timeout=600)
        self.round_view = round_view

    @discord.ui.button(label="Write my clue", style=discord.ButtonStyle.primary, emoji="✏️")
    async def write(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(ClueModal(self.round_view))
        self.stop()


async def advance(game: WavelengthGame, interaction: discord.Interaction) -> None:
    """Start the next round, or finish the game."""
    if not game.next_round():
        await game.finish()
        await interaction.followup.send(
            f"\U0001F4E1 **Wavelength — final scores**\n{game.scoreboard()}\n"
            "-# `/wavelength` to go again."
        )
        return

    view = RoundView(game)
    game.message = await interaction.followup.send(view.clue_text(), view=view, wait=True)


class Wavelength(commands.Cog):
    HELP_ENTRIES = [
        HelpEntry(
            name="wavelength",
            summary="Guess where a secret spot sits on a scale, from one clue",
            category="Games",
            examples=["/wavelength"],
            show_in_help=True,
        )
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="wavelength", description="Party game: read your friends' minds")
    async def wavelength(self, interaction: discord.Interaction) -> None:
        existing = active_game(interaction.channel_id)
        if existing and not existing.finished:
            return await interaction.response.send_message(
                f"There's already a **{existing.name}** game running in this channel.",
                ephemeral=True,
            )

        game = WavelengthGame(interaction.channel, interaction.user)
        register(game)

        async def on_start(inter: discord.Interaction) -> None:
            game.begin()
            game.next_round()
            view = RoundView(game)
            await inter.response.edit_message(
                content=f"\U0001F4E1 **Wavelength** starting with {game.count} players!",
                view=None,
            )
            game.message = await inter.followup.send(view.clue_text(), view=view, wait=True)

        lobby = LobbyView(game, on_start=on_start)
        await interaction.response.send_message(game.lobby_text(), view=lobby)
        game.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Wavelength(bot))
