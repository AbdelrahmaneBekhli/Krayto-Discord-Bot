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
    "moody noir illustration, ink and muted watercolour wash, limited palette of "
    "slate blue and amber, heavy shadow, 1950s small town, cinematic wide shot, "
    "grainy, melancholy, no text, no lettering, no faces, no crowds"
)

SCENES: dict[str, tuple[str, ...]] = {
    narrator_ai.KILL: (
        "a still body lying face down on wet garden stones at grey dawn, "
        "one shoe off, a washing line overhead, back door standing open",
        "an overturned chair in an empty kitchen at first light, a kettle still "
        "steaming, a dark shape on the floor just out of frame",
        "a narrow alley at dawn, a coat crumpled against the brick, rain "
        "beginning, a single streetlamp still burning",
        "a body under a sheet in the middle of a small town square at sunrise, "
        "bicycles abandoned, shutters closed all around",
    ),
    # Dramatic mode: a rescue. The town already learns somebody lived.
    narrator_ai.SAVE: (
        "a dark doorstep at night, a thin wash of blood diluted by rain, an open "
        "doctor's bag beside it, nobody in sight",
        "a bedroom at dawn, bandages and a basin of red water on the floor, the "
        "bed empty and the sheets thrown back, curtains moving",
        "a wet pavement at night lit by one window, dropped surgical scissors "
        "glinting, two sets of footprints leading away",
    ),
    narrator_ai.BLOCKED: (
        "an empty small town street at midnight, every door shut, one interior "
        "light burning behind frosted glass, nothing moving at all",
        "a locked back gate seen from the inside, chain and padlock, long shadows, "
        "an untouched lane beyond it",
    ),
    narrator_ai.QUIET: (
        "an empty small town street at sunrise, milk bottles untouched on every "
        "step, mist in the road, nothing has happened",
        "a quiet kitchen window at dawn seen from outside, condensation, an "
        "undisturbed garden, birds on the fence",
    ),
}

# Discreet mode can't illustrate the rescue without implying who was rescued,
# so it gets atmosphere instead and gives nothing away.
DISCREET_SAVE = (
    "an empty wet street at night, a dark patch on the stones already thinning "
    "in the rain, a door closing in the distance",
    "a deserted lane at first light, one gate swinging open, a dropped bag of "
    "shopping, no sign of anybody",
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
    weather = "clear cold night" if night % 2 else "light rain"
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
