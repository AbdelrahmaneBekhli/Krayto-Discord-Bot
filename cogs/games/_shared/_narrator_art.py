"""
One illustration per night, posted as the closing beat of the story.

Timing is the whole trick. Text narration is prefetched *before* the outcome
exists, because one call covers every ending. An image can't work that way --
four renders to use one would be four times the cost and waste three. So the
picture is started *after* resolution, when we know what actually happened, and
the story drips over the top of it: five beats at `BEAT_DELAY` is about twelve
seconds of cover, which is longer than these models usually take. By the time
the body has been found, the panel is already waiting.

Player names never reach the image provider. They would render as garbled text
in the picture anyway, and there is no reason to hand someone's display name to
a third party to draw a garden with.
"""

from __future__ import annotations

import asyncio
import logging
import random

from cogs import _images as images
from cogs.games._shared import _narrator as narrator
from cogs.games._shared import _narrator_ai as narrator_ai

log = logging.getLogger(__name__)

# Appended to every panel so a game's nights look like one book rather than a
# dozen unrelated pictures.
STYLE = (
    "noir illustration, ink and watercolour, dramatic chiaroscuro lighting, "
    "slate blue shadows with warm amber lamplight, 1950s small town, cinematic "
    "mid shot, clear focal subject, detailed, grainy, melancholy, no text, "
    "no lettering, no watermark"
)

# Every scene names a subject and an action. An earlier version banned people
# from the frame, which produced four variations on "empty street at night" --
# atmospheric, but you could not tell a murder from a quiet night.
SCENES: dict[str, tuple[str, ...]] = {
    narrator_ai.KILL: (
        "a body lying face down on wet garden stones at grey dawn, one arm "
        "outstretched, a white sheet half drawn over it, two villagers standing "
        "back with lanterns, washing line overhead",
        "townspeople crowding a doorway at first light, a still figure slumped "
        "across the threshold, an overturned chair and a kettle on its side "
        "inside, one woman turning away",
        "a covered body on a stretcher being carried through a narrow alley at "
        "dawn, rain falling, neighbours watching from windows above",
        "a body under a sheet in the middle of a small town square at sunrise, a "
        "constable kneeling beside it, villagers gathered in a ring, bicycles "
        "abandoned on the cobbles",
    ),
    # Dramatic mode: a rescue, and it has to look like one.
    narrator_ai.SAVE: (
        "a doctor kneeling over a wounded person in a lamplit doorway at night, "
        "hands pressing a bandage to their side, open medical bag spilling "
        "gauze, rain on the step",
        "two figures dragging a wounded person in from a dark street into warm "
        "lamplight, blood on the stones behind them, a basin and towels waiting",
        "a wounded person propped against a wall under a streetlamp, a healer "
        "winding a bandage around their shoulder, the pair alone in the rain, "
        "relief on the healer's posture",
    ),
    narrator_ai.BLOCKED: (
        "a hooded figure stopped at a chained gate at midnight, hand on the "
        "padlock, a constable's lantern raised behind them, empty street beyond",
        "a locked cell door in a village lock-up at night, a silhouette sitting "
        "on the bench inside, one lamp burning in the corridor",
    ),
    narrator_ai.QUIET: (
        "an empty small town street at sunrise, milk bottles untouched on every "
        "step, mist low in the road, shutters opening, nothing has happened",
        "a woman opening her curtains at dawn onto a quiet undisturbed garden, "
        "birds on the fence, kettle steaming on the sill",
    ),
}

# Discreet mode can't show who was rescued, so it shows the aftermath instead:
# clearly a rescue happened, with no way to tell whose doorstep it was.
DISCREET_SAVE = (
    "an abandoned doctor's bag open on wet cobblestones at night, bloodied gauze "
    "beside it, a trail of footprints leading away into fog, nobody in frame",
    "a dark patch of blood on a rain-slicked step at first light, a dropped "
    "bandage roll unwinding into the gutter, the door shut, street empty",
)


def prompt_for(outcome, mode: str, night: int) -> str | None:
    """The scene for whatever happened, or None if this night can't be drawn."""
    variant = narrator_ai.variant_for(outcome)
    if variant == narrator_ai.SAVE and mode != narrator.DRAMATIC:
        pool = DISCREET_SAVE
    else:
        pool = SCENES.get(variant)
    if not pool:
        return None
    # Weather only -- the scenes set their own time of day, and an hour added
    # here contradicted them ("at sunrise ... clear cold night").
    weather = "cold clear air" if night % 2 else "steady rain"
    return f"{random.choice(pool)}, {weather}. {STYLE}"


def start(game, outcome, night: int):
    """
    Begin rendering tonight's panel. Returns an asyncio Task, or None.

    Fire-and-forget on purpose: `narrator.tell` collects it after the last beat
    and drops it if it isn't ready.
    """
    if game.settings.narration == narrator.OFF or not images.configured():
        return None

    prompt = prompt_for(outcome, game.settings.narration, night)
    if prompt is None:
        return None

    # Seeded off the channel so one game's nights stay visually related, and off
    # the night so they aren't the same picture twice.
    seed = (game.channel.id + night * 7919) % 2_000_000_000
    coro = images.generate(game.bot, prompt, seed=seed)
    try:
        return asyncio.create_task(coro)
    except RuntimeError:  # no running loop (tests)
        coro.close()
        return None
