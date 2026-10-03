from __future__ import annotations

import asyncio
import logging
import random
from collections import Counter
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands

from cogs import _images as images
from cogs import _llm as llm
from cogs._help_registry import HelpEntry
from cogs.games._shared import _confirm
from cogs.games._shared import _narrator as narrator
from cogs.games._shared import _narrator_ai as narrator_ai
from cogs.games._shared import _narrator_art as narrator_art
from cogs.games._shared._core import BaseGame, Palette, active_game, register
from cogs.games._shared._lobby import LobbyView
from cogs.games._shared._narrator import NightOutcome

log = logging.getLogger(__name__)

MAX_OPTIONS = 25  # Discord's hard cap on select options

# How long resolution will wait for AI narration that hasn't landed yet. It was
# started when the night began, so by now it has had the whole deliberation to
# finish; this is only the tail. Past it, the built-in templates take over.
AI_GRACE_SECONDS = 4.0


@dataclass(frozen=True)
class Role:
    key: str
    name: str
    emoji: str
    blurb: str
    acts_at_night: bool
    prompt: str = ""
    # Mafia and Police are their own plural, so this can't be name + "s".
    plural: str = ""

    def counted(self, n: int) -> str:
        """'1 Doctor', '2 Doctors', '0 Police'."""
        return f"{n} {self.name if n == 1 else (self.plural or self.name + 's')}"


ROLES: dict[str, Role] = {
    "mafia": Role(
        "mafia", "Mafia", "\U0001F52A",
        "Each night you pick someone to eliminate. Win when you equal the town.",
        True, "Who do you want to eliminate tonight?", "Mafia",
    ),
    "detective": Role(
        "detective", "Detective", "\U0001F50D",
        "Each night you investigate one player and learn whether they're Mafia.",
        True, "Who do you want to investigate?", "Detectives",
    ),
    "doctor": Role(
        "doctor", "Doctor", "\U0001F489",
        "Each night you protect one player from being killed. You may protect yourself.",
        True, "Who do you want to protect?", "Doctors",
    ),
    "police": Role(
        "police", "Police", "\U0001F693",
        "Each night you detain one player: they can't use a night action, "
        "and they can't be killed.",
        True, "Who do you want to detain tonight?", "Police",
    ),
    "villager": Role(
        "villager", "Villager", "\U0001F9D1‍\U0001F33E",
        "No night action. Work out who the Mafia are, and vote.",
        False, "", "Villagers",
    ),
}

CONFIGURABLE = ("mafia", "detective", "doctor", "police")


@dataclass
class Settings:
    mafia: int = 1
    detective: int = 1
    doctor: int = 1
    police: int = 0
    narration: str = narrator.DRAMATIC

    def special_total(self) -> int:
        return self.mafia + self.detective + self.doctor + self.police

    def summary(self) -> str:
        bits = []
        for key in CONFIGURABLE:
            n = getattr(self, key)
            if n:
                bits.append(f"{ROLES[key].emoji} {ROLES[key].counted(n)}")
        return " · ".join(bits) if bits else "no special roles"

    def validate(self, players: int) -> str | None:
        """Returns a human-readable problem, or None if the setup is playable."""
        if self.mafia < 1:
            return "You need at least 1 Mafia."
        if self.special_total() > players:
            return (
                f"That's {self.special_total()} special roles but only {players} players. "
                "Lower some counts or get more people in."
            )
        if self.mafia * 2 >= players:
            return (
                f"{self.mafia} Mafia in a {players}-player game is unwinnable for the town. "
                f"Use at most {(players - 1) // 2}."
            )
        return None


@dataclass
class Player:
    member: discord.Member
    role: Role
    alive: bool = True

    @property
    def id(self) -> int:
        return self.member.id

    @property
    def name(self) -> str:
        return self.member.display_name


@dataclass
class NightActions:
    """Each actor's own target, so several Doctors/Police resolve independently."""

    kill: int | None = None                                    # agreed Mafia target
    protect: dict[int, int] = field(default_factory=dict)      # doctor id -> target
    detain: dict[int, int] = field(default_factory=dict)       # police id -> target
    investigate: dict[int, int] = field(default_factory=dict)  # detective id -> target
    submitted: set[int] = field(default_factory=set)           # actors done this night


class MafiaGame(BaseGame):
    name = "Mafia"
    emoji = "\U0001F576️"
    min_players = 4
    max_players = MAX_OPTIONS

    def __init__(self, channel, host, bot: commands.Bot) -> None:
        super().__init__(channel, host)
        self.bot = bot  # narration needs the shared aiohttp session
        self.settings = Settings()
        self.cast: dict[int, Player] = {}
        self.day = 0
        self.night_actions = NightActions()
        self.votes: dict[int, int | None] = {}  # voter id -> target id, None = skip
        self.log: list[str] = []
        # AI narration for the night in progress, written while players decide.
        self.story: asyncio.Task | None = None

    # -- narration --------------------------------------------------------

    def start_story(self) -> None:
        """
        Kick off AI narration for the night that is just beginning.

        Fire-and-forget on purpose: it runs through the deliberation, and if it
        never finishes nothing waits on it beyond `AI_GRACE_SECONDS`.
        """
        self.story = None
        if self.settings.narration == narrator.OFF or not llm.configured():
            return
        dead = len(self.cast) - len(self.living)
        coro = narrator_ai.generate(
            self.bot,
            night=self.day + 1,
            alive=len(self.living),
            dead=dead,
            mode=self.settings.narration,
        )
        try:
            self.story = asyncio.create_task(coro)
        except RuntimeError:  # no running loop (tests)
            coro.close()

    async def prepared_story(self) -> dict[str, list[str]] | None:
        """Collect the night's AI script, or None if it isn't ready in time."""
        task, self.story = self.story, None
        if task is None:
            return None
        try:
            return await asyncio.wait_for(task, AI_GRACE_SECONDS)
        except asyncio.TimeoutError:
            log.info("AI narration missed the window; using templates")
        except Exception:
            log.warning("AI narration failed", exc_info=True)
        return None

    def restart(self) -> None:
        """
        Deal the same lobby a fresh game.

        Everything derived from the old deal goes: a half-written night would
        otherwise arrive during the new one, and the old cast is what the
        roster and the win check read from.
        """
        if self.story is not None:
            self.story.cancel()
            self.story = None
        self.cast = {}
        self.day = 0
        self.night_actions = NightActions()
        self.votes = {}
        self.assign_roles()

    def fact(self, text: str) -> str:
        """
        A plain statement of what happened.

        When the narrator is on it has just spent five beats on this, so the
        factual line drops to a caption rather than competing as a headline.
        It stays in full when there is no story to have told it.
        """
        if self.settings.narration == narrator.OFF:
            return text
        return f"-# {text}"

    def narrator_label(self) -> str:
        """e.g. 'Narrator: dramatic · ✨ AI · 🖼️ panels'."""
        label = narrator.NARRATION_LABELS[self.settings.narration]
        if self.settings.narration == narrator.OFF:
            return label
        if llm.configured():
            label += " · ✨ AI"
        if images.configured():
            label += " · \U0001F5BC️ panels"
        return label

    async def finish(self) -> None:
        # Don't leave a half-written night running after the game is over.
        if self.story is not None:
            self.story.cancel()
            self.story = None
        await super().finish()

    # -- roster ----------------------------------------------------------

    @property
    def living(self) -> list[Player]:
        return [p for p in self.cast.values() if p.alive]

    @property
    def living_mafia(self) -> list[Player]:
        return [p for p in self.living if p.role.key == "mafia"]

    @property
    def living_town(self) -> list[Player]:
        return [p for p in self.living if p.role.key != "mafia"]

    def player(self, user_id: int) -> Player | None:
        return self.cast.get(user_id)

    def night_actors(self) -> list[Player]:
        return [p for p in self.living if p.role.acts_at_night]

    # -- setup -----------------------------------------------------------

    def assign_roles(self) -> None:
        pool: list[Role] = []
        for key in CONFIGURABLE:
            pool += [ROLES[key]] * getattr(self.settings, key)
        pool += [ROLES["villager"]] * (self.count - len(pool))
        random.shuffle(pool)

        self.cast = {
            member.id: Player(member=member, role=role)
            for member, role in zip(self.roster, pool)
        }
        self.started = True

    def lobby_embed(self) -> discord.Embed:
        embed = super().lobby_embed()
        embed.add_field(
            name="Roles",
            value=(
                f"{self.settings.summary()}\neveryone else is a Villager\n"
                f"-# \U0001F3A5 {self.narrator_label()}"
            ),
            inline=False,
        )
        problem = self.settings.validate(self.count)
        if problem and self.count >= self.min_players:
            embed.colour = Palette.WARN
            embed.set_footer(text=f"⚠️ {problem}")
        return embed

    # -- night resolution -------------------------------------------------

    def resolve_night(self) -> NightOutcome:
        """Apply the night and report what happened, including the near-misses."""
        acts = self.night_actions

        # Police act first and can't be blocked, so detentions always land.
        detained = set(acts.detain.values())

        # A detained Doctor never gets to protect anyone.
        protected = {
            target for doctor_id, target in acts.protect.items()
            if doctor_id not in detained
        }
        # Being detained also keeps you alive.
        mafia_all_detained = bool(self.living_mafia) and all(
            m.id in detained for m in self.living_mafia
        )
        outcome = NightOutcome(mafia_blocked=mafia_all_detained)

        if acts.kill is not None and not mafia_all_detained:
            target = self.player(acts.kill)
            if target and target.alive:
                outcome.attacked = target
                # A save is worth narrating, so record which one landed. The
                # Doctor takes the credit when both cover the same person.
                if target.id in protected:
                    outcome.saved_by_doctor = True
                elif target.id in detained:
                    outcome.saved_by_police = True
                else:
                    target.alive = False
                    outcome.victim = target

        results: dict[int, str] = {}
        for det_id, target_id in acts.investigate.items():
            if det_id in detained:
                results[det_id] = "You were detained — no result tonight."
                continue
            target = self.player(target_id)
            if target is None:
                continue
            verdict = "**is** Mafia" if target.role.key == "mafia" else "is **not** Mafia"
            results[det_id] = f"{target.name} {verdict}."

        outcome.results = results
        return outcome

    # -- voting -----------------------------------------------------------

    def tally(self) -> Counter:
        return Counter(v for v in self.votes.values() if v is not None)

    def vote_result(self) -> tuple[Player | None, str]:
        """Plurality wins; any tie means nobody goes."""
        counts = self.tally()
        if not counts:
            return None, "Nobody voted for anyone."
        ranked = counts.most_common()
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            return None, "The vote was tied — nobody is eliminated."
        target = self.player(ranked[0][0])
        if target is None:
            return None, "The vote didn't land on anyone."
        target.alive = False
        return target, f"**{target.name}** is voted out — they were {target.role.emoji} **{target.role.name}**."

    # -- win check ---------------------------------------------------------

    def winner(self) -> str | None:
        if not self.living_mafia:
            return "town"
        if len(self.living_mafia) >= len(self.living_town):
            return "mafia"
        return None

    def add_roster(self, embed: discord.Embed) -> discord.Embed:
        """Alive list always; the out list only once somebody is out."""
        embed.add_field(
            name=f"Alive ({len(self.living)})",
            value=", ".join(p.name for p in self.living) or "nobody",
            inline=False,
        )
        dead = [p for p in self.cast.values() if not p.alive]
        if dead:
            embed.add_field(
                name="Out",
                value=", ".join(f"{p.name} {p.role.emoji}" for p in dead),
                inline=False,
            )
        return embed

    def final_embed(self, who: str) -> discord.Embed:
        town = who == "town"
        embed = discord.Embed(
            title="\U0001F3C6 Town wins!" if town else "\U0001F52A Mafia wins!",
            description=(
                "Every Mafia is gone."
                if town
                else "The Mafia equal the town — nobody can stop them now."
            ),
            colour=Palette.TOWN_WIN if town else Palette.MAFIA_WIN,
        )
        embed.add_field(
            name="Everyone's role",
            value="\n".join(
                f"{p.role.emoji} **{p.name}** — {p.role.name}"
                + ("" if p.alive else " *(out)*")
                for p in self.cast.values()
            ),
            inline=False,
        )
        return embed


# ---------------------------------------------------------------------------
# Setup (host only, ephemeral)
# ---------------------------------------------------------------------------


def setup_content(game: MafiaGame) -> str:
    """The host's ephemeral setup panel text, rebuilt after every change."""
    problem = game.settings.validate(game.count)
    note = f"\n⚠️ {problem}" if problem else "\n✅ Setup looks good."
    mode = game.settings.narration
    writer = "✨ written fresh by AI each night" if (
        mode != narrator.OFF and llm.configured()
    ) else "built-in script"
    if mode != narrator.OFF and images.configured():
        writer += " · \U0001F5BC️ illustrated"
    return (
        f"**Roles:** {game.settings.summary()}\n"
        f"**Narrator:** {narrator.NARRATION_LABELS[mode].split(': ')[1]} — "
        f"{narrator.NARRATION_BLURBS[mode]}\n"
        f"-# {writer}{note}"
    )


class SetupSelect(discord.ui.Select):
    """Base for the host's setup dropdowns: apply, redraw panel, redraw lobby."""

    def __init__(self, game: MafiaGame, lobby_view: LobbyView, **kwargs) -> None:
        super().__init__(**kwargs)
        self.game = game
        self.lobby_view = lobby_view

    def apply(self) -> None:
        raise NotImplementedError

    async def callback(self, interaction: discord.Interaction) -> None:
        self.apply()
        await interaction.response.edit_message(
            content=setup_content(self.game),
            view=SetupView(self.game, self.lobby_view),
        )
        if self.game.message:
            try:
                await self.game.message.edit(
                    embed=self.game.lobby_embed(), view=self.lobby_view
                )
            except discord.HTTPException:
                pass


class NarrationSelect(SetupSelect):
    def __init__(self, game: MafiaGame, lobby_view: LobbyView) -> None:
        current = game.settings.narration
        super().__init__(
            game,
            lobby_view,
            placeholder=f"\U0001F3A5 {narrator.NARRATION_LABELS[current]}",
            options=[
                discord.SelectOption(
                    label=narrator.NARRATION_LABELS[mode].split(": ")[1].capitalize(),
                    value=mode,
                    description=narrator.NARRATION_BLURBS[mode][:100],
                    default=(mode == current),
                )
                for mode in (narrator.DRAMATIC, narrator.DISCREET, narrator.OFF)
            ],
        )

    def apply(self) -> None:
        self.game.settings.narration = self.values[0]


class CountSelect(SetupSelect):
    def __init__(self, game: MafiaGame, key: str, lobby_view: LobbyView) -> None:
        role = ROLES[key]
        current = getattr(game.settings, key)
        lowest = 1 if key == "mafia" else 0
        super().__init__(
            game,
            lobby_view,
            placeholder=f"{role.emoji} {role.name}: {current}",
            options=[
                discord.SelectOption(
                    label=role.counted(n), value=str(n), default=(n == current),
                )
                for n in range(lowest, 6)
            ],
        )
        self.key = key

    def apply(self) -> None:
        setattr(self.game.settings, self.key, int(self.values[0]))


class SetupView(discord.ui.View):
    def __init__(self, game: MafiaGame, lobby_view: LobbyView) -> None:
        super().__init__(timeout=600)
        # Five action rows is Discord's cap, and this uses all five.
        for key in CONFIGURABLE:
            self.add_item(CountSelect(game, key, lobby_view))
        self.add_item(NarrationSelect(game, lobby_view))


# ---------------------------------------------------------------------------
# Shared phase view
# ---------------------------------------------------------------------------


class MafiaView(discord.ui.View):
    """
    Base for every in-game phase: carries the game and the host's controls.

    Restart and End can fire from any phase, so they live here once rather
    than four times. Each phase supplies its own `embed()`.
    """

    def __init__(self, game: MafiaGame, *, timeout: float = 1800) -> None:
        super().__init__(timeout=timeout)
        self.game = game

    def embed(self) -> discord.Embed:  # pragma: no cover - each phase defines it
        raise NotImplementedError

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
        problem = g.settings.validate(g.count)
        if problem:
            return await interaction.response.send_message(problem, ephemeral=True)

        async def confirmed(inter: discord.Interaction) -> None:
            if g.finished:
                return
            self.stop()
            g.restart()
            if g.message:
                try:
                    await g.message.edit(
                        embed=discord.Embed(
                            title=f"{g.emoji} Mafia",
                            description="-# Restarted by the host.",
                            colour=Palette.OVER,
                        ),
                        view=None,
                    )
                except discord.HTTPException:
                    pass
            view = RoleRevealView(g)
            g.message = await g.channel.send(embed=view.embed(), view=view)

        await _confirm.ask(
            interaction,
            question="Restart the game?",
            detail=(
                f"Same {g.count} players, roles dealt again from scratch. "
                "This round's progress is lost."
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
            emb = g.final_embed("town") if not g.living_mafia else g.final_embed("mafia")
            emb.title = f"{g.emoji} Mafia — ended"
            emb.description = "The host called it. Everyone's role is below."
            emb.colour = Palette.OVER
            await g.channel.send(embed=emb)

        await _confirm.ask(
            interaction,
            question="End the game now?",
            detail="Everyone's role is revealed and the game stops. No winner.",
            label="End it",
            emoji="\U0001F6D1",
            on_confirm=confirmed,
        )


# ---------------------------------------------------------------------------
# Night
# ---------------------------------------------------------------------------


class TargetSelect(discord.ui.Select):
    def __init__(self, game: MafiaGame, actor: Player, night_view: "NightView") -> None:
        candidates = [p for p in game.living if p.id != actor.id or actor.role.key == "doctor"]
        options = [
            discord.SelectOption(label=p.name, value=str(p.id))
            for p in candidates[:MAX_OPTIONS]
        ]
        super().__init__(placeholder=actor.role.prompt, options=options)
        self.game = game
        self.actor = actor
        self.night_view = night_view

    async def callback(self, interaction: discord.Interaction) -> None:
        target_id = int(self.values[0])
        target = self.game.player(target_id)
        acts = self.game.night_actions
        key = self.actor.role.key

        if key == "mafia":
            acts.kill = target_id
        elif key == "doctor":
            acts.protect[self.actor.id] = target_id
        elif key == "police":
            acts.detain[self.actor.id] = target_id
        elif key == "detective":
            acts.investigate[self.actor.id] = target_id

        acts.submitted.add(self.actor.id)
        await interaction.response.edit_message(
            content=f"✅ Locked in: **{target.name if target else '?'}**", view=None
        )
        await self.night_view.after_submit(interaction)


class NightActionPrompt(discord.ui.View):
    def __init__(self, game: MafiaGame, actor: Player, night_view: "NightView") -> None:
        super().__init__(timeout=600)
        self.add_item(TargetSelect(game, actor, night_view))


class NightView(MafiaView):
    def __init__(self, game: MafiaGame) -> None:
        super().__init__(game)
        # Start writing tonight's story now, while everyone is still choosing.
        game.start_story()

    def embed(self) -> discord.Embed:
        g = self.game
        actors = g.night_actors()
        done = len(g.night_actions.submitted & {p.id for p in actors})
        emb = discord.Embed(
            title=f"\U0001F319 Night {g.day + 1}",
            description="Everyone close your eyes.",
            colour=Palette.NIGHT,
        )
        g.add_roster(emb)
        emb.set_footer(
            text=f"{done}/{len(actors)} night actions in · tap below if you have one"
        )
        return emb

    @staticmethod
    def closed_embed(night_number: int) -> discord.Embed:
        """
        What the night card becomes once the night is over.

        It used to re-render the full roster, which repeated everything the
        upcoming day card was about to say -- and, because the day counter had
        already advanced, retitled itself as the *next* night.
        """
        return discord.Embed(
            title=f"\U0001F319 Night {night_number}",
            description="-# Everyone acted. The night is over.",
            colour=Palette.NIGHT,
        )

    async def after_submit(self, interaction: discord.Interaction) -> None:
        g = self.game
        actors = {p.id for p in g.night_actors()}
        if actors.issubset(g.night_actions.submitted):
            await self.resolve(interaction)
        elif g.message:
            try:
                await g.message.edit(embed=self.embed(), view=self)
            except discord.HTTPException:
                pass

    async def resolve(self, interaction: discord.Interaction) -> None:
        g = self.game
        self.stop()
        outcome = g.resolve_night()
        victim = outcome.victim
        night_number = g.day + 1

        for det_id, text in outcome.results.items():
            member = g.cast[det_id].member
            try:
                await member.send(f"\U0001F50D Investigation result: {text}")
            except discord.HTTPException:
                pass  # DMs closed; they can re-check with "My role"

        g.day += 1
        headline = (
            f"☠️ **{victim.name}** didn't survive the night — "
            f"they were {victim.role.emoji} **{victim.role.name}**."
            if victim
            else "\U0001F54A️ Nobody died last night."
        )
        if g.message:
            try:
                await g.message.edit(
                    embed=self.closed_embed(night_number), view=None
                )
            except discord.HTTPException:
                pass

        # The story goes out before the facts, so the embed reads as the
        # morning report rather than a spoiler for it. The panel is started here
        # -- now that the outcome is known -- and the beats drip over the top of
        # it, which is all the time it needs.
        prepared = await g.prepared_story()
        art = narrator_art.start(g, outcome, night_number)
        await narrator.tell(
            g.channel,
            narrator.night_beats(
                outcome, g.living, night_number, g.settings.narration, prepared
            ),
            title=f"\U0001F319 Night {night_number}",
            colour=Palette.NIGHT,
            art=art,
        )

        won = g.winner()
        if won:
            await g.finish()
            await narrator.tell(
                g.channel,
                narrator.finale_beats(won, g.settings.narration),
                title="\U0001F3AC The last word",
                colour=Palette.TOWN_WIN if won == "town" else Palette.MAFIA_WIN,
            )
            await g.channel.send(content=g.fact(headline), embed=g.final_embed(won))
            return

        day_view = DayView(g, headline)
        g.message = await g.channel.send(embed=day_view.embed(), view=day_view)

    @discord.ui.button(
        label="My night action", style=discord.ButtonStyle.primary, emoji="\U0001F311"
    )
    async def act_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        g = self.game
        actor = g.player(interaction.user.id)
        if actor is None:
            return await interaction.response.send_message(
                "You're not in this game.", ephemeral=True
            )
        if not actor.alive:
            return await interaction.response.send_message(
                "You're out — enjoy the show.", ephemeral=True
            )
        if not actor.role.acts_at_night:
            return await interaction.response.send_message(
                f"{actor.role.emoji} You're a **{actor.role.name}** — "
                "no night action. Sit tight.",
                ephemeral=True,
            )

        header = f"{actor.role.emoji} You are **{actor.role.name}**."
        if actor.role.key == "mafia":
            mates = [m.name for m in g.living_mafia if m.id != actor.id]
            header += f"\nYour team: {', '.join(mates)}" if mates else "\nYou work alone."
            if g.night_actions.kill is not None:
                picked = g.player(g.night_actions.kill)
                if picked:
                    header += f"\n-# Current target: **{picked.name}** (last pick wins)"

        await interaction.response.send_message(
            header, view=NightActionPrompt(g, actor, self), ephemeral=True
        )

    @discord.ui.button(label="Force dawn", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.game.is_host(interaction.user):
            return await interaction.response.send_message(
                "Only the host can end the night early.", ephemeral=True
            )
        await interaction.response.send_message("Ending the night...", ephemeral=True)
        await self.resolve(interaction)


# ---------------------------------------------------------------------------
# Day and voting
# ---------------------------------------------------------------------------


class DayView(MafiaView):
    def __init__(self, game: MafiaGame, headline: str) -> None:
        super().__init__(game)
        self.headline = headline

    def embed(self) -> discord.Embed:
        emb = discord.Embed(
            title=f"☀️ Day {self.game.day}",
            description=self.game.fact(self.headline),
            colour=Palette.DAY,
        )
        self.game.add_roster(emb)
        emb.set_footer(text="Talk it out. The host starts the vote when you're ready.")
        return emb

    @discord.ui.button(label="Start the vote", style=discord.ButtonStyle.primary, emoji="\U0001F5F3️")
    async def vote_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.game.is_host(interaction.user):
            return await interaction.response.send_message(
                "Only the host can start the vote.", ephemeral=True
            )
        self.stop()
        self.game.votes = {}
        view = VoteView(self.game)
        await interaction.response.edit_message(embed=self.embed(), view=None)
        self.game.message = await self.game.channel.send(
            embed=view.embed(), view=view
        )

    @discord.ui.button(label="My role", style=discord.ButtonStyle.secondary, emoji="\U0001F3AD")
    async def role_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await send_role_card(self.game, interaction)


class VoteSelect(discord.ui.Select):
    def __init__(self, game: MafiaGame, vote_view: "VoteView") -> None:
        options = [
            discord.SelectOption(label=p.name, value=str(p.id)) for p in game.living[:MAX_OPTIONS - 1]
        ]
        options.append(
            discord.SelectOption(label="Skip — nobody", value="skip", emoji="\U0001F6AB")
        )
        super().__init__(placeholder="Who goes?", options=options)
        self.game = game
        self.vote_view = vote_view

    async def callback(self, interaction: discord.Interaction) -> None:
        choice = self.values[0]
        target_id = None if choice == "skip" else int(choice)
        self.game.votes[interaction.user.id] = target_id
        target = self.game.player(target_id) if target_id else None
        await interaction.response.edit_message(
            content=f"✅ Voted: **{target.name if target else 'skip'}**", view=None
        )
        await self.vote_view.after_vote(interaction)


class VotePrompt(discord.ui.View):
    def __init__(self, game: MafiaGame, vote_view: "VoteView") -> None:
        super().__init__(timeout=600)
        self.add_item(VoteSelect(game, vote_view))


class VoteView(MafiaView):
    def __init__(self, game: MafiaGame) -> None:
        super().__init__(game)

    def embed(self) -> discord.Embed:
        g = self.game
        counts = g.tally()
        standing = "\n".join(
            f"**{n}** — {g.player(pid).name if g.player(pid) else '?'}"
            for pid, n in counts.most_common()
        ) or "No votes yet."
        emb = discord.Embed(
            title=f"\U0001F5F3️ Day {g.day} vote",
            description=standing,
            colour=Palette.VOTE,
        )
        skips = sum(1 for v in g.votes.values() if v is None)
        tail = f" · {skips} skipping" if skips else ""
        emb.set_footer(text=f"{len(g.votes)}/{len(g.living)} voted{tail}")
        return emb

    async def after_vote(self, interaction: discord.Interaction) -> None:
        g = self.game
        if len(g.votes) >= len(g.living):
            await self.close(interaction)
        elif g.message:
            try:
                await g.message.edit(embed=self.embed(), view=self)
            except discord.HTTPException:
                pass

    async def close(self, interaction: discord.Interaction) -> None:
        g = self.game
        self.stop()
        anyone_voted = bool(g.tally())
        # Render the final tally before the elimination lands: vote_result()
        # marks the loser dead, and the card counts "x/len(living)", so doing
        # this afterwards reported three of two people having voted.
        final = self.embed()
        voted_out, verdict = g.vote_result()
        if g.message:
            try:
                await g.message.edit(embed=final, view=None)
            except discord.HTTPException:
                pass

        await narrator.tell(
            g.channel,
            narrator.vote_beats(
                voted_out, g.settings.narration, anyone_voted=anyone_voted
            ),
            title=f"\U0001F5F3️ Day {g.day} verdict",
            colour=Palette.VOTE,
        )

        won = g.winner()
        if won:
            await g.finish()
            await narrator.tell(
                g.channel,
                narrator.finale_beats(won, g.settings.narration),
                title="\U0001F3AC The last word",
                colour=Palette.TOWN_WIN if won == "town" else Palette.MAFIA_WIN,
            )
            await g.channel.send(content=g.fact(verdict), embed=g.final_embed(won))
            return

        g.night_actions = NightActions()
        night = NightView(g)
        g.message = await g.channel.send(
            content=g.fact(verdict), embed=night.embed(), view=night
        )

    @discord.ui.button(label="Vote", style=discord.ButtonStyle.primary, emoji="\U0001F5F3️")
    async def cast_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        g = self.game
        voter = g.player(interaction.user.id)
        if voter is None:
            return await interaction.response.send_message(
                "You're not in this game.", ephemeral=True
            )
        if not voter.alive:
            return await interaction.response.send_message(
                "The dead don't vote.", ephemeral=True
            )
        await interaction.response.send_message(
            "Your vote is secret until the tally.",
            view=VotePrompt(g, self),
            ephemeral=True,
        )

    @discord.ui.button(label="Close the vote", style=discord.ButtonStyle.danger, emoji="⏱️")
    async def close_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.game.is_host(interaction.user):
            return await interaction.response.send_message(
                "Only the host can close the vote.", ephemeral=True
            )
        await interaction.response.send_message("Closing the vote...", ephemeral=True)
        await self.close(interaction)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def send_role_card(game: MafiaGame, interaction: discord.Interaction) -> None:
    player = game.player(interaction.user.id)
    if player is None:
        return await interaction.response.send_message(
            "You're not in this game.", ephemeral=True
        )
    text = f"{player.role.emoji} You are **{player.role.name}**\n{player.role.blurb}"
    if player.role.key == "mafia":
        mates = [m.name for m in game.living_mafia if m.id != player.id]
        text += f"\n\n**Your team:** {', '.join(mates) if mates else 'you work alone'}"
    if not player.alive:
        text += "\n\n-# You're out of the game."
    await interaction.response.send_message(text, ephemeral=True)


class RoleRevealView(MafiaView):
    """Shown once at game start so everyone can privately read their card."""

    def __init__(self, game: MafiaGame) -> None:
        super().__init__(game)
        self.seen: set[int] = set()  # players who have looked at their card

    def embed(self) -> discord.Embed:
        g = self.game
        emb = discord.Embed(
            title=f"\U0001F576️ Mafia — {g.count} players",
            description=f"{g.settings.summary()}\neveryone else is a Villager",
            colour=Palette.LOBBY,
        )
        waiting = [p.name for p in g.cast.values() if p.id not in self.seen]
        if waiting and self.seen:
            emb.add_field(
                name=f"Looked ({len(self.seen)}/{len(g.cast)})",
                value="waiting on " + ", ".join(waiting),
                inline=False,
            )
        emb.set_footer(
            text="Everyone tap Reveal my role — only you can see it. "
                 "Night falls once everyone has looked."
        )
        return emb

    async def begin(self) -> None:
        """Night falls. Safe to call without an un-responded interaction."""
        if self.is_finished():
            return
        self.stop()
        g = self.game
        if g.message:
            try:
                await g.message.edit(
                    content=None,
                    embed=discord.Embed(
                        title="\U0001F3AD Roles are in",
                        description="Night falls...",
                        colour=Palette.NIGHT,
                    ),
                    view=None,
                )
            except discord.HTTPException:
                pass
        night = NightView(g)
        g.message = await g.channel.send(embed=night.embed(), view=night)

    @discord.ui.button(label="Reveal my role", style=discord.ButtonStyle.primary, emoji="\U0001F3AD")
    async def reveal(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await send_role_card(self.game, interaction)

        player = self.game.player(interaction.user.id)
        if player is None or player.id in self.seen:
            return
        self.seen.add(player.id)

        # Once everyone has looked there is nothing left to wait for.
        if self.seen >= set(self.game.cast):
            return await self.begin()
        if self.game.message:
            try:
                await self.game.message.edit(embed=self.embed(), view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Start anyway", style=discord.ButtonStyle.success, emoji="▶️")
    async def go(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        """Host override, for when somebody has wandered off."""
        if not self.game.is_host(interaction.user):
            return await interaction.response.send_message(
                "Only the host can begin.", ephemeral=True
            )
        await interaction.response.defer()
        await self.begin()


class Mafia(commands.Cog):
    HELP_ENTRIES = [
        HelpEntry(
            name="mafia",
            summary="Social deduction: find the Mafia before they outnumber the town",
            category="Games",
            examples=[
                "/mafia  — then everyone taps Join",
                "Roles → 2 Mafia, 1 Detective, 1 Doctor  (good for 7–9)",
                "Roles → 1 Mafia, 1 Detective, 0 Doctor  (fast 4–5 player game)",
                "Roles → Narrator: discreet  (story, but no free information)",
            ],
            show_in_help=True,
            details=(
                "**4+ players.** The Mafia know each other. Nobody else knows anything.\n\n"
                "**1. Lobby** — everyone taps **Join**. The host taps **Roles** to pick how "
                "many Mafia, Detective, Doctor and Police to deal; everyone left over is a "
                "Villager. Then **Start**, and everyone taps **Reveal my role** — only you "
                "can see yours.\n\n"
                "**2. Night** 🌙 — tap **My night action** for a private menu:\n"
                "🔪 **Mafia** choose someone to eliminate (your team shares one target)\n"
                "🔍 **Detective** investigate someone — you learn if they're Mafia\n"
                "💉 **Doctor** protect someone from being killed, including yourself\n"
                "🚔 **Police** detain someone — they can't act and can't be killed\n"
                "🧑‍🌾 **Villager** no action, just sit tight\n"
                "Night resolves as soon as everyone has acted.\n\n"
                "**3. Day** ☀️ — 🎥 the **narrator** tells the night back to you line by "
                "line: who was wandering about, what nearly happened, and who didn't make "
                "it. Then the bot states the facts. Talk, accuse, defend. When you're "
                "ready the host taps **Start the vote**.\n\n"
                "**4. Vote** 🗳️ — everyone alive votes privately. Most votes is eliminated "
                "and their role is revealed. **A tie eliminates nobody.** Then night falls "
                "again.\n\n"
                "**Winning** — the Town wins when every Mafia is gone. The Mafia win the "
                "moment they equal the rest of the town.\n\n"
                "**The narrator** 🎥 — set under **Roles**:\n"
                "**Dramatic** names the player a Doctor pulled back, so the town learns "
                "who the Mafia went for\n"
                "**Discreet** keeps the same story but gives nothing away\n"
                "**Off** skips straight to the facts\n"
                "Beats arrive one at a time and **ping the people they name**. "
                "If an AI provider is set up, the night is written fresh while "
                "you're all still choosing, and an illustration of the morning "
                "closes it — both land without costing you any extra waiting.\n\n"
                "**The host** 🔁 can **Restart** (same players, roles dealt again) or "
                "**End game** (everyone's role revealed, no winner) from any phase. "
                "Both ask first.\n\n"
                "-# The dead can still read the channel, so no hints once you're out."
            ),
        )
    ]

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="mafia", description="Host a game of Mafia")
    async def mafia(self, interaction: discord.Interaction) -> None:
        existing = active_game(interaction.channel_id)
        if existing and not existing.finished:
            return await interaction.response.send_message(
                f"There's already a **{existing.name}** game running in this channel.",
                ephemeral=True,
            )

        game = MafiaGame(interaction.channel, interaction.user, interaction.client)
        register(game)

        async def on_setup(inter: discord.Interaction) -> None:
            await inter.response.send_message(
                setup_content(game),
                view=SetupView(game, lobby),
                ephemeral=True,
            )

        async def on_start(inter: discord.Interaction) -> None:
            problem = game.settings.validate(game.count)
            if problem:
                return await inter.response.send_message(problem, ephemeral=True)
            game.assign_roles()
            view = RoleRevealView(game)
            await inter.response.edit_message(
                content=None, embed=view.embed(), view=view
            )
            game.message = await inter.original_response()

        lobby = LobbyView(game, on_start=on_start, on_setup=on_setup, setup_label="Roles")
        await interaction.response.send_message(embed=game.lobby_embed(), view=lobby)
        game.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    # Said once at startup so a mistyped key shows up here, not mid-game.
    log.info(
        "Mafia narrator — text: %s · panels: %s", llm.describe(), images.describe()
    )
    await bot.add_cog(Mafia(bot))
