from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry
from cogs.games._shared._core import BaseGame, Palette, active_game, bar, register
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
    return f"**{left}**  ◀━━━━━━━━━▶  **{right}**"


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

    def lobby_embed(self) -> discord.Embed:
        embed = super().lobby_embed()
        embed.description = (
            "One player gets a secret spot on a scale and gives a one-word clue. "
            "Everyone else guesses where it was."
        )
        return embed


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

    def _base_embed(self) -> discord.Embed:
        g = self.game
        return discord.Embed(
            title=f"\U0001F4E1 Round {g.round_index + 1}/{len(g.order)}",
            description=spectrum_line(g.left, g.right),
            colour=Palette.ROUND,
        )

    def clue_embed(self) -> discord.Embed:
        g = self.game
        psychic = g.psychic.display_name if g.psychic else "?"
        emb = self._base_embed()
        emb.set_footer(text=f"{psychic} is the Psychic · waiting for a clue...")
        return emb

    def guessing_embed(self) -> discord.Embed:
        g = self.game
        remaining = len(g.guessers) - len(g.guesses)
        tail = "" if remaining else " · everyone's in, reveal when ready"
        psychic = g.psychic.display_name if g.psychic else "?"
        emb = self._base_embed()
        emb.add_field(name=f"{psychic} says", value=f"**“{g.clue}”**", inline=False)
        emb.set_footer(text=f"{len(g.guesses)}/{len(g.guessers)} guessed{tail}")
        return emb

    async def refresh_public(self) -> None:
        if self.game.message:
            try:
                await self.game.message.edit(embed=self.guessing_embed(), view=self)
            except discord.HTTPException:
                pass

    async def show_guessing(self, interaction: discord.Interaction) -> None:
        self.clear_items()
        self.add_item(self.guess_btn)
        self.add_item(self.reveal_btn)
        await interaction.response.edit_message(embed=self.guessing_embed(), view=self)

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
        await interaction.response.edit_message(embed=self.reveal_embed(), view=None)
        await advance(g, interaction)

    def reveal_embed(self) -> discord.Embed:
        g = self.game
        emb = discord.Embed(
            title=f"\U0001F4E1 Round {g.round_index + 1} — the spot was {g.target}",
            description=f"{spectrum_line(g.left, g.right)}\n{gauge(g.target)}",
            colour=Palette.REVEAL,
        )

        lines = []
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

        emb.add_field(name=f"Clue: “{g.clue}”", value="\n".join(lines), inline=False)
        emb.add_field(name="Scores", value=g.scoreboard(), inline=False)
        return emb


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
        emb = discord.Embed(
            title="\U0001F4E1 Wavelength — final scores",
            description=game.scoreboard(),
            colour=Palette.REVEAL,
        )
        emb.set_footer(text="/wavelength to go again")
        await interaction.followup.send(embed=emb)
        return

    view = RoundView(game)
    game.message = await interaction.followup.send(
        embed=view.clue_embed(), view=view, wait=True
    )


class Wavelength(commands.Cog):
    HELP_ENTRIES = [
        HelpEntry(
            name="wavelength",
            summary="Guess where a secret spot sits on a scale, from one clue",
            category="Games",
            examples=[
                "/wavelength  — then everyone taps Join",
                "Scale: Underrated ◀▶ Overrated · spot 9 · clue “pineapple on pizza”",
                "Scale: Cold ◀▶ Hot · spot 2 · clue “a forgotten cup of tea”",
            ],
            show_in_help=True,
            details=(
                "**3+ players.** One player knows the answer and has to get it across in "
                "one word.\n\n"
                "**1. Lobby** — everyone taps **Join**, the host taps **Start**.\n\n"
                "**2. The Psychic** 🔮 — one player per round. They tap the button and "
                "privately see a scale, like **Boring ◀━━▶ Exciting**, and a secret spot "
                "from **1 to 10**. They then write one clue that sits exactly on that spot. "
                "No numbers, no pointing, no 'a bit left of'.\n\n"
                "**3. Everyone else** 🎯 — tap **Guess** and privately pick a band from "
                "1 to 10. You can change it right up until the reveal.\n\n"
                "**4. Reveal** 👀 — the host or the Psychic reveals the spot and everyone "
                "scores:\n"
                "🎯 exact band — **4 points**\n"
                "✨ one off — **2 points**\n"
                "• two off — **1 point**\n"
                "further — nothing\n\n"
                "The **Psychic scores the average of their guessers**, so a clue that lands "
                "the whole room beats a clever one only your best friend gets.\n\n"
                "Everyone is Psychic exactly once, then the final scores go up. "
                "45 different scales, and a game never repeats one."
            ),
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
                content=None,
                embed=discord.Embed(
                    title="\U0001F4E1 Wavelength",
                    description=f"Starting with {game.count} players!",
                    colour=Palette.ROUND,
                ),
                view=None,
            )
            game.message = await inter.followup.send(
                embed=view.clue_embed(), view=view, wait=True
            )

        lobby = LobbyView(game, on_start=on_start)
        await interaction.response.send_message(embed=game.lobby_embed(), view=lobby)
        game.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Wavelength(bot))
