from __future__ import annotations

import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry
from cogs.games._shared import _confirm
from cogs.games._shared._core import BaseGame, Palette, active_game, register
from cogs.games._shared._lobby import LobbyView

SLOTS = 10

# How long the scores sit on their own before the next round lands under them.
# The round used to end and restart in the same instant, which buried the
# reveal and left people scrolling up to find out how they had done. Longer
# tables take longer to read, so this grows a little with the player count.
INTERMISSION = 7.0
INTERMISSION_PER_PLAYER = 0.6
INTERMISSION_MAX = 13.0

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


def spectrum_line(left: str, right: str) -> str:
    """The scale, with the numbers people actually pick between on the ends."""
    return f"**1 · {left}**  ◀━━━━━━━━━▶  **{right} · {SLOTS}**"


def _scale_label(left: str, right: str) -> str:
    """Same scale squeezed into a modal field label, which caps at 45 chars."""
    label = f"1={left} … {SLOTS}={right}"
    if len(label) <= 45:
        return label
    room = (45 - len(f"1= … {SLOTS}=")) // 2
    return f"1={left[:room]} … {SLOTS}={right[:room]}"


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

    def restart(self) -> None:
        """Same lobby, scores wiped, a fresh turn order and fresh spectrums."""
        self.round_index = -1
        self.unused = SPECTRUMS.copy()
        self.begin()
        self.next_round()

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


class ClueModal(discord.ui.Modal):
    """
    The Psychic's secret spot and their clue box, in one step.

    The spot rides along in the modal's own title and field label, so opening
    this *is* seeing your spot -- no separate reveal message, and no second
    button to get from there to here.
    """

    def __init__(self, round_view: "RoundView") -> None:
        g = round_view.game
        super().__init__(title=f"Your secret spot: {g.target} of {SLOTS}")
        self.round_view = round_view
        self.clue = discord.ui.TextInput(
            label=_scale_label(g.left, g.right),
            placeholder="one word or phrase that sits exactly on your spot",
            max_length=80,
        )
        self.add_item(self.clue)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.round_view.game.clue = str(self.clue).strip()
        await self.round_view.open_guessing(interaction)


class GuessSelect(discord.ui.Select):
    def __init__(self, round_view: "RoundView") -> None:
        # Only the two ends carry a description. A slider drawn beside every
        # number just asked people to read a dot's position off a value that
        # was already written next to it.
        g = round_view.game
        options = [
            discord.SelectOption(
                label=str(i),
                value=str(i),
                description=(g.left if i == 1 else g.right if i == SLOTS else None),
            )
            for i in range(1, SLOTS + 1)
        ]
        super().__init__(placeholder="Where on the scale?", options=options)
        self.round_view = round_view

    async def callback(self, interaction: discord.Interaction) -> None:
        guess = int(self.values[0])
        g = self.round_view.game
        g.guesses[interaction.user.id] = guess
        await interaction.response.edit_message(
            content=f"Locked in: **{guess}**", view=None
        )
        # Nothing left to wait for once every guesser is in.
        if len(g.guesses) >= len(g.guessers):
            await self.round_view.do_reveal()
        else:
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
        psychic = g.psychic.display_name if g.psychic else "?"
        emb = self._base_embed()
        emb.add_field(name=f"{psychic} says", value=f"**“{g.clue}”**", inline=False)
        waiting = [m.display_name for m in g.guessers if m.id not in g.guesses]
        if waiting:
            emb.add_field(
                name=f"Guessed ({len(g.guesses)}/{len(g.guessers)})",
                value="waiting on " + ", ".join(waiting),
                inline=False,
            )
        emb.set_footer(
            text="Tap Guess and pick 1–10 · the spot shows once everyone has guessed"
        )
        return emb

    async def refresh_public(self) -> None:
        if self.game.message:
            try:
                await self.game.message.edit(embed=self.guessing_embed(), view=self)
            except discord.HTTPException:
                pass

    async def open_guessing(self, interaction: discord.Interaction) -> None:
        """
        Put the board into guessing mode after the Psychic submits a clue.

        The modal opens from the Psychic's own button, so `interaction` here
        belongs to that private exchange, not to the public card. Editing the
        interaction's message put the whole guessing board inside an ephemeral
        only the Psychic could see, while everyone else watched a card that
        still said "waiting for a clue".
        """
        self.clear_items()
        self.add_item(self.guess_btn)
        self.add_item(self.reveal_btn)
        self.add_item(self.restart_btn)
        self.add_item(self.end_btn)

        g = self.game
        await interaction.response.send_message(
            f"✅ Clue sent: **“{g.clue}”**\n"
            f"Your spot was **{g.target}**. Sit tight.",
            ephemeral=True,
        )
        if g.message:
            try:
                await g.message.edit(embed=self.guessing_embed(), view=self)
            except discord.HTTPException:
                pass

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
        # Straight into the modal: it carries the spot and the scale itself.
        await interaction.response.send_modal(ClueModal(self))

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

    async def _host_only(self, interaction: discord.Interaction) -> bool:
        if self.game.is_host(interaction.user):
            return True
        await interaction.response.send_message(
            f"Only the host ({self.game.host.display_name}) can do that.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(
        label="Restart", style=discord.ButtonStyle.secondary, emoji="\U0001F501", row=4
    )
    async def restart_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._host_only(interaction):
            return
        g = self.game

        async def confirmed(inter: discord.Interaction) -> None:
            if g.finished:
                return
            self.stop()
            g.restart()
            if g.message:
                try:
                    await g.message.edit(
                        embed=discord.Embed(
                            title=f"{g.emoji} Wavelength",
                            description="-# Restarted by the host.",
                            colour=Palette.OVER,
                        ),
                        view=None,
                    )
                except discord.HTTPException:
                    pass
            view = RoundView(g)
            g.message = await g.channel.send(embed=view.clue_embed(), view=view)

        await _confirm.ask(
            interaction,
            question="Restart the game?",
            detail=(
                f"Same {g.count} players, scores back to zero, everyone is "
                "Psychic again. This round is lost."
            ),
            label="Restart",
            emoji="\U0001F501",
            on_confirm=confirmed,
        )

    @discord.ui.button(
        label="End game", style=discord.ButtonStyle.danger, emoji="\U0001F6D1", row=4
    )
    async def end_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._host_only(interaction):
            return
        g = self.game

        async def confirmed(inter: discord.Interaction) -> None:
            if g.finished:
                return
            self.stop()
            await g.finish()
            if g.message:
                try:
                    await g.message.edit(view=None)
                except discord.HTTPException:
                    pass
            emb = discord.Embed(
                title="\U0001F4E1 Wavelength — ended",
                description=g.scoreboard() or "No scores yet.",
                colour=Palette.OVER,
            )
            emb.set_footer(text="The host called it · /wavelength to go again")
            await g.channel.send(embed=emb)

        await _confirm.ask(
            interaction,
            question="End the game now?",
            detail="Scores so far go up and the game stops.",
            label="End it",
            emoji="\U0001F6D1",
            on_confirm=confirmed,
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
        await interaction.response.defer()
        await self.do_reveal()

    async def do_reveal(self) -> None:
        """
        Show the spot and move on. Safe to call without a live interaction.

        reveal_embed() awards the points, so stopping first keeps a late guess
        landing at the same moment as the host's button from scoring twice.
        """
        if self.is_finished():
            return
        self.stop()
        g = self.game
        emb = self.reveal_embed()
        more_rounds = g.round_index + 1 < len(g.order)
        emb.set_footer(
            text="Next round in a moment…" if more_rounds
            else "That was the last round — final scores coming up…"
        )
        if g.message:
            try:
                await g.message.edit(embed=emb, view=None)
            except discord.HTTPException:
                pass
        await intermission(g)
        await advance(g)

    def reveal_embed(self) -> discord.Embed:
        g = self.game
        emb = discord.Embed(
            title=f"\U0001F4E1 Round {g.round_index + 1} — the spot was {g.target}",
            description=spectrum_line(g.left, g.right),
            colour=Palette.REVEAL,
        )

        # Closest first, so the reveal reads as a ranking rather than a roster.
        ordered = sorted(
            g.guessers,
            key=lambda m: (
                g.guesses.get(m.id) is None,
                abs(g.guesses.get(m.id, 0) - g.target),
            ),
        )

        lines = []
        for member in ordered:
            guess = g.guesses.get(member.id)
            if guess is None:
                lines.append(f"• {member.display_name} — didn't guess")
                continue
            points = score_for(guess, g.target)
            g.scores[member.id] = g.scores.get(member.id, 0) + points
            mark = "\U0001F3AF" if points == 4 else ("✨" if points else "•")
            gap = abs(guess - g.target)
            how = "spot on" if gap == 0 else f"{gap} off"
            lines.append(
                f"{mark} **{guess}** — {member.display_name} · {how} · **+{points}**"
            )

        # The Psychic scores the average of their guessers, so a good clue pays.
        # Read only the guessers' own picks, never the whole guess map, so the
        # Psychic can never end up averaging against themselves.
        landed = [g.guesses[m.id] for m in g.guessers if m.id in g.guesses]
        scored = [score_for(v, g.target) for v in landed]
        bonus = round(sum(scored) / len(scored)) if scored else 0
        if g.psychic:
            g.scores[g.psychic.id] = g.scores.get(g.psychic.id, 0) + bonus
            spread = sorted(landed)
            reach = f"{spread[0]}–{spread[-1]}" if spread else "nobody"
            lines.append(
                f"\U0001F52E **{g.psychic.display_name}** (Psychic) — "
                f"the room landed {reach} · **+{bonus}**"
            )

        emb.add_field(name=f"Clue: “{g.clue}”", value="\n".join(lines), inline=False)
        emb.add_field(name="Scores", value=g.scoreboard(), inline=False)
        return emb


async def intermission(game: WavelengthGame) -> None:
    """Leave the scores up long enough to read, with the typing dots showing."""
    delay = min(
        INTERMISSION_MAX,
        INTERMISSION + INTERMISSION_PER_PLAYER * len(game.players),
    )
    try:
        async with game.channel.typing():
            await asyncio.sleep(delay)
    except discord.HTTPException:
        await asyncio.sleep(delay)


async def advance(game: WavelengthGame) -> None:
    """Start the next round, or finish the game."""
    if not game.next_round():
        await game.finish()
        emb = discord.Embed(
            title="\U0001F4E1 Wavelength — final scores",
            description=game.scoreboard(),
            colour=Palette.REVEAL,
        )
        emb.set_footer(text="/wavelength to go again")
        await game.channel.send(embed=emb)
        return

    view = RoundView(game)
    game.message = await game.channel.send(embed=view.clue_embed(), view=view)


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
                "**The host** 🔁 can **Restart** (same players, scores reset) or "
                "**End game** (scores so far, then stop) at any point. Both ask first.\n\n"
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
            game.message = await game.channel.send(
                embed=view.clue_embed(), view=view
            )

        lobby = LobbyView(game, on_start=on_start)
        await interaction.response.send_message(embed=game.lobby_embed(), view=lobby)
        game.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Wavelength(bot))
