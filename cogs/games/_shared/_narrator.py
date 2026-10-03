from __future__ import annotations

import asyncio
import io
import logging
import random
from dataclasses import dataclass, field

import discord

log = logging.getLogger(__name__)

# Beats ping the people they name, which is why each one is its own plain-text
# message: Discord fires no notification for a mention inside an embed, nor for
# one added by editing a message, so a single growing embed could never ping.
PING = discord.AllowedMentions(users=True, roles=False, everyone=False)
NO_PING = discord.AllowedMentions.none()

# Pacing. A fixed gap made long beats arrive before the last one was read and
# short ones linger, so the pause is now the time it takes to read the beat
# that just landed. Casual reading of prose on a phone is roughly four words a
# second; the floor keeps one-liners from snapping past, the ceiling keeps a
# long beat from stalling the game.
WORDS_PER_SECOND = 4.0
MIN_BEAT_DELAY = 3.2
MAX_BEAT_DELAY = 8.0
LEAD_IN_DELAY = 1.8  # before the first beat, under the header

# Kept for callers that want one number; the real pacing is read_time().
BEAT_DELAY = 4.0


def read_time(beat: str) -> float:
    """How long to leave a beat on screen before the next one lands."""
    words = len(beat.split())
    return max(MIN_BEAT_DELAY, min(MAX_BEAT_DELAY, words / WORDS_PER_SECOND))


def as_narration(beat: str) -> str:
    """
    Render a beat as a quote block.

    Consecutive bot messages get no separation in Discord, so plain narration
    ran together into a wall. The quote bar gives every beat its own left edge
    and marks the narrator apart from anything players type.
    """
    return "\n".join(
        f"> {line}" if line.strip() else ">" for line in beat.split("\n")
    )

OFF, DISCREET, DRAMATIC = "off", "discreet", "dramatic"

NARRATION_LABELS = {
    OFF: "Narrator: off",
    DISCREET: "Narrator: discreet",
    DRAMATIC: "Narrator: dramatic",
}

NARRATION_BLURBS = {
    OFF: "Just the facts, no story.",
    DISCREET: "Full drama, but never reveals who the Mafia went for.",
    DRAMATIC: "Full drama, and names the player a Doctor pulled back.",
}


# ---------------------------------------------------------------------------
# Beat pools
#
# Every line is a `str.format` template. The context always carries {a} {b} {c}
# (living bystanders, shuffled) plus {victim} / {attacked} / {role} where the
# pool is only reachable with one. Pools needing two distinct bystanders are
# kept separate so a four-player endgame never formats a name it doesn't have.
# ---------------------------------------------------------------------------

FIRST_NIGHT = (
    "The last porch light on the street clicks off. The town holds its breath.",
    "Curtains close one by one, until the only thing still awake is the dark.",
    "Somewhere a dog starts barking and will not stop. Nobody goes to see why.",
    "The streetlamps hum. The pavement is still warm. Everything looks normal.",
    "Doors lock. Not all of them. Not the ones that matter.",
)

LATER_NIGHT = (
    "Night {n}. Nobody bothers pretending they are going to sleep.",
    "Night {n}, and the town has learned to count heads before dark.",
    "The quiet is different now. It is the quiet of people listening.",
    "Night {n}. Somebody in this town has done it {n_minus} time{s} already.",
    "Every window in town is lit. It has not helped yet.",
    "The clock in the square grinds toward midnight. It always has.",
)

# Red-herring cameos: pure atmosphere, zero information. The two-name versions
# come first because the fake-out reads better with a second person in it.
CAMEO_PAIR = (
    "{a} hears a scream in the hallway. Murder?\n"
    "No — just {b}, three drinks in, arguing with nobody. {a} joins the party.",

    "{a} is sure someone is behind the hedge, and turns.\n"
    "It is {b}, holding a bin bag, mortified.",

    "A floorboard cracks like a gunshot. {a} freezes on the stairs.\n"
    "Down the hall, {b} is asleep with the television on.",

    "{a} and {b} walk home together, because nobody should be alone tonight.\n"
    "They part at the crossroads.",

    "{a} texts {b}: *you up?*\n"
    "{b} is up. {b} has been at the window for an hour and won't say why.",

    "{a} hears a car idle outside, then pull away.\n"
    "{b}, two doors down, hears nothing. One of them is telling the truth.",

    "{a} swears the gate was shut. {b} swears {a} left it open.\n"
    "Neither of them looks outside.",
)

CAMEO_SOLO = (
    "{a} checks the lock. Then checks it again. Then sits down facing the door.",
    "{a} is awake, counting the ceiling. {a} has done this every night this week.",
    "A shadow crosses {a}'s window and does not come back. {a} decides it was a cat.",
    "{a} pours a drink and does not touch it.",
)

# The approach. Deliberately nameless — naming anyone here would leak.
STALK = (
    "Somewhere across town, a door opens that should not.",
    "Footsteps. Unhurried. Someone who knows exactly which house they want.",
    "A gate swings. Nobody closes it.",
    "There is a knock. It is answered. That was the mistake.",
    "Something moves between the houses, low and patient and already decided.",
    "A light goes on in an upstairs room, and goes out very fast.",
)

STRIKE = (
    "A sound that is not quite a scream, because it does not get the chance.",
    "Glass. Then nothing. The nothing is worse.",
    "One short struggle, over in the time it takes to read this line.",
    "The barking stops. All at once, everywhere.",
    "Whatever happens next happens quietly, and the town sleeps through it.",
)

DISCOVERY = (
    "Dawn comes grey and ordinary. In the back garden, a body is laid out on the stones.\n"
    "It is {victim}. {role}.",

    "The milk is on the step. The door is open. {victim} is just inside it.\n"
    "{role}, and not a secret any more.",

    "They find {victim} at first light, face turned toward the house "
    "like they almost made it.\n{role}.",

    "Somebody screams for real this time. {victim} is in the square, "
    "and {victim} is not getting up.\n{role}.",

    "The sun comes up on {victim}, and on the thing that was done to {victim}.\n"
    "{role}. The town will be chewing on that all day.",
)

# Attacked but protected. DRAMATIC names the target; DISCREET gives the same
# beat without telling the town who the Mafia went for.
SAVE_NAMED = (
    "A stranger is kneeling over the body before dawn. Sleeves up, hands steady.\n"
    "{attacked} wakes in their own bed, no idea how close that was.",

    "{attacked} goes down, and should stay down.\n"
    "Someone was already running. By morning {attacked} is at breakfast. Pale. Alive.",

    "They nearly lost {attacked} last night.\n"
    "Somebody here bought those twenty seconds and is saying nothing about it.",

    "Blood on {attacked}'s doorstep, and no body to go with it.\n"
    "Someone got there first. Someone always seems to.",
)

SAVE_QUIET = (
    "A stranger kneels over the body before dawn, sleeves up.\n"
    "By sunrise there is no body — only a dark patch on the stones.",

    "There is blood on a doorstep somewhere in this town and no name for it.\n"
    "Somebody was saved. Neither of them is talking.",

    "The Mafia went out last night and came back empty-handed.\n"
    "Not because they missed. Because someone was in the way.",
)

BLOCKED = (
    "The ones who go out at night did not get out at all.\n"
    "Somewhere there is a locked room and a very bad temper.",

    "Nothing moved last night. Not one door, not one step.\n"
    "Whatever was supposed to happen was held somewhere under a light, "
    "answering questions.",
)

QUIET = (
    "And then — nothing.\n"
    "No scream, no glass, no running feet. The night simply ends.",

    "The town waits all night for the sound it has learned to expect.\n"
    "It never comes. Somehow that is harder.",

    "Dawn. Full head count. Everybody breathing.\n"
    "Nobody believes it either.",
)

DAWN = (
    "The sun comes up on a town that will spend all day accusing itself.",
    "Morning. Everyone counts. Everyone counts again.",
    "Coffee gets made. Nobody drinks it. The talking starts.",
)

# -- vote ---------------------------------------------------------------

VOTE_OUT = (
    "The hands go up before the arguing has even stopped.\n"
    "{victim} is walked out of the square still explaining.\n{role}.",

    "It takes nine minutes to decide and nine seconds to do.\n"
    "{victim} does not get a last word in. {role}.",

    "The town has made up its mind, and the town has never once apologised "
    "for that.\n{victim} goes. {role}.",

    "Somebody says the name. Somebody else repeats it. "
    "After that it is only arithmetic.\n{victim}. {role}.",
)

VOTE_TIE = (
    "The count comes out level, and the square goes very quiet.\n"
    "No hands, no verdict. Everyone walks home with the same neighbours "
    "they suspected this morning.",

    "Dead even. Nobody moves.\n"
    "The town has just handed whoever did this another night.",
)

VOTE_NONE = (
    "Nobody will say a name out loud.\n"
    "The town files home in silence, and the night is already waiting.",
)

# -- finale -------------------------------------------------------------

TOWN_WIN = (
    "The last one is pulled out of the crowd, and the crowd does not let go.\n"
    "It is over. The lights stay on tonight.",

    "No more knocks. No more open doors.\n"
    "The town got there — late, loud, and only just.",
)

MAFIA_WIN = (
    "There are not enough of you left to outvote them, and they know it.\n"
    "They do not even bother with the dark any more.",

    "The town looks around the table and finally understands the arithmetic.\n"
    "It has been their town for a while now. Nobody told you.",
)


# ---------------------------------------------------------------------------
# Facts in, beats out
# ---------------------------------------------------------------------------


@dataclass
class NightOutcome:
    """What actually happened at night, as facts the narrator can dramatise."""

    victim: object | None = None    # Player who died, if anyone did
    attacked: object | None = None  # the Mafia's target, dead or not
    saved_by_doctor: bool = False
    saved_by_police: bool = False
    mafia_blocked: bool = False     # every living Mafia was detained
    results: dict[int, str] = field(default_factory=dict)  # detective id -> text

    @property
    def rescued(self) -> bool:
        return self.victim is None and self.attacked is not None and (
            self.saved_by_doctor or self.saved_by_police
        )


def _role_line(player) -> str:
    return f"{player.role.emoji} **{player.role.name}**"


def _slots(bystanders: list[str], **extra) -> dict:
    """Name slots {a} {b} {c}, padded so a short roster never breaks format()."""
    pool = bystanders + ["someone", "a neighbour", "nobody in particular"]
    return {"a": pool[0], "b": pool[1], "c": pool[2], **extra}


def _bystanders(living, *exclude) -> list[str]:
    """Living players who aren't part of the real story, in random order."""
    skip = {p.id for p in exclude if p is not None}
    names = [p.member.mention for p in living if p.id not in skip]
    random.shuffle(names)
    return names


def _narration_slots(outcome: NightOutcome, living, mode: str) -> tuple[dict, int]:
    """
    Every name the narration might need, for templates and AI beats alike.

    Also returns how many of {a} {b} {c} are real players rather than padding,
    since a cameo about two people needs two people to exist.
    """
    victim, attacked = outcome.victim, outcome.attacked
    # In dramatic mode the rescued player is about to be named, so keep them out
    # of the throwaway cameo; in discreet mode they're fair game as cover.
    named_later = attacked if (mode == DRAMATIC and outcome.rescued) else None
    bystanders = _bystanders(living, victim, named_later)

    slots = _slots(bystanders)
    if victim is not None:
        slots["victim"] = victim.member.mention
        slots["role"] = _role_line(victim)
    if attacked is not None:
        slots["attacked"] = attacked.member.mention
    return slots, len(bystanders)


def _from_prepared(
    outcome: NightOutcome, living, prepared: dict[str, list[str]], mode: str
) -> list[str] | None:
    """Use the AI's script for whichever ending actually happened."""
    from cogs.games._shared import _narrator_ai  # late: _narrator_ai imports us

    beats = prepared.get(_narrator_ai.variant_for(outcome))
    if not beats:
        return None
    slots, _ = _narration_slots(outcome, living, mode)
    return _narrator_ai.fill(beats, slots)


def night_beats(
    outcome: NightOutcome,
    living,
    night: int,
    mode: str,
    prepared: dict[str, list[str]] | None = None,
) -> list[str]:
    """
    Build the night's narration. `living` is the roster *after* resolution.

    `prepared` is the AI's script for every possible ending, written during the
    night while players were still deciding (see `_narrator_ai`). We pick the
    branch that actually happened and fill the names in. Anything missing or
    malformed falls through to the built-in pools, so narration never fails.
    """
    if mode == OFF:
        return []

    victim, attacked = outcome.victim, outcome.attacked

    if prepared:
        beats = _from_prepared(outcome, living, prepared, mode)
        if beats:
            return beats

    slots, bystanders = _narration_slots(outcome, living, mode)
    beats: list[str] = []

    # 1. Atmosphere.
    if night <= 1:
        beats.append(random.choice(FIRST_NIGHT))
    else:
        beats.append(random.choice(LATER_NIGHT).format(
            n=night, n_minus=night - 1, s="" if night == 2 else "s",
        ))

    # 2. A cameo that means nothing, so the next line means more.
    if bystanders >= 2:
        beats.append(random.choice(CAMEO_PAIR).format(**slots))
    elif bystanders:
        beats.append(random.choice(CAMEO_SOLO).format(**slots))

    # 3. What actually happened.
    if victim is not None:
        beats.append(random.choice(STALK))
        beats.append(random.choice(STRIKE))
        beats.append(random.choice(DISCOVERY).format(**slots))
    elif outcome.rescued:
        beats.append(random.choice(STALK))
        beats.append(random.choice(STRIKE))
        if mode == DRAMATIC:
            beats.append(random.choice(SAVE_NAMED).format(**slots))
        else:
            beats.append(random.choice(SAVE_QUIET))
    elif outcome.mafia_blocked:
        beats.append(random.choice(BLOCKED))
        beats.append(random.choice(DAWN))
    else:
        beats.append(random.choice(QUIET))
        beats.append(random.choice(DAWN))

    return beats


def vote_beats(victim, mode: str, *, anyone_voted: bool) -> list[str]:
    if mode == OFF:
        return []
    if victim is not None:
        return [random.choice(VOTE_OUT).format(
            victim=victim.member.mention, role=_role_line(victim),
        )]
    return [random.choice(VOTE_TIE if anyone_voted else VOTE_NONE)]


def finale_beats(who: str, mode: str) -> list[str]:
    if mode == OFF:
        return []
    return [random.choice(TOWN_WIN if who == "town" else MAFIA_WIN)]


# ---------------------------------------------------------------------------
# Telling it
# ---------------------------------------------------------------------------


MAX_BEAT_CHARS = 1900  # Discord's content limit is 2000; leave room

# How long the closing panel gets after the last beat lands. It was started at
# resolution and the drip has already covered ~12s of it, so this is the tail.
ART_GRACE_SECONDS = 8.0


async def _pause(channel, delay: float) -> None:
    """Hold the beat, showing the typing indicator while it hangs."""
    try:
        async with channel.typing():
            await asyncio.sleep(delay)
    except discord.HTTPException:
        await asyncio.sleep(delay)


async def _collect_art(art) -> discord.File | None:
    """Pick up the night's panel if it made it in time. Never raises."""
    if art is None:
        return None
    try:
        result = await asyncio.wait_for(art, ART_GRACE_SECONDS)
    except asyncio.TimeoutError:
        log.info("Night panel missed the window; posting without it")
        return None
    except Exception:
        log.warning("Night panel failed", exc_info=True)
        return None
    if not result:
        return None
    data, extension = result
    return discord.File(io.BytesIO(data), filename=f"night.{extension}")


async def tell(
    channel,
    beats: list[str],
    *,
    title: str,
    colour: discord.Colour,
    delay: float = BEAT_DELAY,
    art=None,
) -> None:
    """
    Post a header card, then each beat as its own message, paced.

    One message per beat is what makes the mentions notify, and it's also the
    better drip: every line arrives as a fresh message rather than an edit
    nobody's client highlights.

    `art` is an in-flight illustration (see `_narrator_art`). It closes the
    story once the last beat has landed, and is dropped if it isn't ready.
    """
    if not beats:
        if art is not None:
            art.cancel()
        return

    try:
        await channel.send(
            embed=discord.Embed(title=title, colour=colour), allowed_mentions=NO_PING
        )
    except discord.HTTPException:
        return  # narration is flavour: never let it take the game down

    for index, beat in enumerate(beats):
        # Pause for as long as the *previous* beat takes to read, so the gap
        # matches what the reader is actually doing.
        await _pause(channel, LEAD_IN_DELAY if index == 0 else read_time(beats[index - 1]))
        try:
            await channel.send(
                as_narration(beat)[:MAX_BEAT_CHARS], allowed_mentions=PING
            )
        except discord.HTTPException:
            if art is not None:
                art.cancel()
            return

    # Let the closing line land before the picture arrives under it.
    await _pause(channel, read_time(beats[-1]))
    panel = await _collect_art(art)
    if panel is not None:
        try:
            await channel.send(file=panel, allowed_mentions=NO_PING)
        except discord.HTTPException:
            pass
