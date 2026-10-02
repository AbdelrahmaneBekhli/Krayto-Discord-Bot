from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands

from cogs._help_registry import HelpEntry
from cogs.games._shared._core import BaseGame, Palette, active_game, register
from cogs.games._shared._lobby import LobbyView

MAX_OPTIONS = 25  # Discord's hard cap on select options


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

    def __init__(self, channel, host) -> None:
        super().__init__(channel, host)
        self.settings = Settings()
        self.cast: dict[int, Player] = {}
        self.day = 0
        self.night_actions = NightActions()
        self.votes: dict[int, int | None] = {}  # voter id -> target id, None = skip
        self.log: list[str] = []

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
            value=f"{self.settings.summary()}\neveryone else is a Villager",
            inline=False,
        )
        problem = self.settings.validate(self.count)
        if problem and self.count >= self.min_players:
            embed.colour = Palette.WARN
            embed.set_footer(text=f"⚠️ {problem}")
        return embed

    # -- night resolution -------------------------------------------------

    def resolve_night(self) -> tuple[Player | None, dict[int, str]]:
        """Apply the night. Returns (victim or None, detective id -> result text)."""
        acts = self.night_actions

        # Police act first and can't be blocked, so detentions always land.
        detained = set(acts.detain.values())

        # A detained Doctor never gets to protect anyone.
        protected = {
            target for doctor_id, target in acts.protect.items()
            if doctor_id not in detained
        }
        # Being detained also keeps you alive.
        protected |= detained

        victim: Player | None = None
        mafia_all_detained = bool(self.living_mafia) and all(
            m.id in detained for m in self.living_mafia
        )
        if acts.kill is not None and not mafia_all_detained:
            target = self.player(acts.kill)
            if target and target.alive and target.id not in protected:
                target.alive = False
                victim = target

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

        return victim, results

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


class CountSelect(discord.ui.Select):
    def __init__(self, game: MafiaGame, key: str, lobby_view: LobbyView) -> None:
        role = ROLES[key]
        current = getattr(game.settings, key)
        lowest = 1 if key == "mafia" else 0
        options = [
            discord.SelectOption(
                label=role.counted(n),
                value=str(n),
                default=(n == current),
            )
            for n in range(lowest, 6)
        ]
        super().__init__(placeholder=f"{role.emoji} {role.name}: {current}", options=options)
        self.game = game
        self.key = key
        self.lobby_view = lobby_view

    async def callback(self, interaction: discord.Interaction) -> None:
        setattr(self.game.settings, self.key, int(self.values[0]))
        problem = self.game.settings.validate(self.game.count)
        note = f"\n⚠️ {problem}" if problem else "\n✅ Setup looks good."
        await interaction.response.edit_message(
            content=f"**Roles:** {self.game.settings.summary()}{note}",
            view=SetupView(self.game, self.lobby_view),
        )
        if self.game.message:
            try:
                await self.game.message.edit(
                    embed=self.game.lobby_embed(), view=self.lobby_view
                )
            except discord.HTTPException:
                pass


class SetupView(discord.ui.View):
    def __init__(self, game: MafiaGame, lobby_view: LobbyView) -> None:
        super().__init__(timeout=600)
        for key in CONFIGURABLE:
            self.add_item(CountSelect(game, key, lobby_view))


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


class NightView(discord.ui.View):
    def __init__(self, game: MafiaGame) -> None:
        super().__init__(timeout=1800)
        self.game = game

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
        victim, results = g.resolve_night()

        for det_id, text in results.items():
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
                await g.message.edit(embed=self.embed(), view=None)
            except discord.HTTPException:
                pass

        won = g.winner()
        if won:
            await g.finish()
            await interaction.followup.send(content=headline, embed=g.final_embed(won))
            return

        day_view = DayView(g, headline)
        g.message = await interaction.followup.send(
            embed=day_view.embed(), view=day_view, wait=True
        )

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


class DayView(discord.ui.View):
    def __init__(self, game: MafiaGame, headline: str) -> None:
        super().__init__(timeout=1800)
        self.game = game
        self.headline = headline

    def embed(self) -> discord.Embed:
        emb = discord.Embed(
            title=f"☀️ Day {self.game.day}",
            description=self.headline,
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
        self.game.message = await interaction.followup.send(
            embed=view.embed(), view=view, wait=True
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


class VoteView(discord.ui.View):
    def __init__(self, game: MafiaGame) -> None:
        super().__init__(timeout=1800)
        self.game = game

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
        _, verdict = g.vote_result()
        if g.message:
            try:
                await g.message.edit(embed=self.embed(), view=None)
            except discord.HTTPException:
                pass

        won = g.winner()
        if won:
            await g.finish()
            await interaction.followup.send(content=verdict, embed=g.final_embed(won))
            return

        g.night_actions = NightActions()
        night = NightView(g)
        g.message = await interaction.followup.send(
            content=verdict, embed=night.embed(), view=night, wait=True
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


class RoleRevealView(discord.ui.View):
    """Shown once at game start so everyone can privately read their card."""

    def __init__(self, game: MafiaGame) -> None:
        super().__init__(timeout=1800)
        self.game = game

    @discord.ui.button(label="Reveal my role", style=discord.ButtonStyle.primary, emoji="\U0001F3AD")
    async def reveal(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await send_role_card(self.game, interaction)

    @discord.ui.button(label="Everyone's ready", style=discord.ButtonStyle.success, emoji="▶️")
    async def go(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not self.game.is_host(interaction.user):
            return await interaction.response.send_message(
                "Only the host can begin.", ephemeral=True
            )
        self.stop()
        night = NightView(self.game)
        await interaction.response.edit_message(
            content=None,
            embed=discord.Embed(
                title="\U0001F3AD Roles are in",
                description="Night falls...",
                colour=Palette.NIGHT,
            ),
            view=None,
        )
        self.game.message = await interaction.followup.send(
            embed=night.embed(), view=night, wait=True
        )


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
                "**3. Day** ☀️ — the bot says who died and what they were. Talk, accuse, "
                "defend. When you're ready the host taps **Start the vote**.\n\n"
                "**4. Vote** 🗳️ — everyone alive votes privately. Most votes is eliminated "
                "and their role is revealed. **A tie eliminates nobody.** Then night falls "
                "again.\n\n"
                "**Winning** — the Town wins when every Mafia is gone. The Mafia win the "
                "moment they equal the rest of the town.\n\n"
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

        game = MafiaGame(interaction.channel, interaction.user)
        register(game)

        async def on_setup(inter: discord.Interaction) -> None:
            await inter.response.send_message(
                f"**Roles:** {game.settings.summary()}",
                view=SetupView(game, lobby),
                ephemeral=True,
            )

        async def on_start(inter: discord.Interaction) -> None:
            problem = game.settings.validate(game.count)
            if problem:
                return await inter.response.send_message(problem, ephemeral=True)
            game.assign_roles()
            view = RoleRevealView(game)
            embed = discord.Embed(
                title=f"\U0001F576️ Mafia — {game.count} players",
                description=f"{game.settings.summary()}\neveryone else is a Villager",
                colour=Palette.LOBBY,
            )
            embed.set_footer(text="Everyone tap Reveal my role — only you can see it.")
            await inter.response.edit_message(content=None, embed=embed, view=view)
            game.message = await inter.original_response()

        lobby = LobbyView(game, on_start=on_start, on_setup=on_setup, setup_label="Roles")
        await interaction.response.send_message(embed=game.lobby_embed(), view=lobby)
        game.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Mafia(bot))
