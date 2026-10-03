"""
AI narration for Mafia, written *during* the night so it costs no visible wait.

The night phase is thirty seconds or more of people deciding, which is plenty
of time for one completion. So while they decide, we ask for every ending at
once -- somebody died, somebody was saved, nothing happened, nobody got out --
each written with `{victim}`-style placeholders instead of names. When the
night resolves we already have the right version and only have to fill the
names in, so the story appears instantly.

That ordering has a second benefit: the model is asked for the script before
the outcome exists, and is never sent the roster or who holds which role. It
cannot leak what it was never told.
"""

from __future__ import annotations

import logging
import random
import re

from cogs import _llm as llm
from cogs.games._shared import _narrator as narrator

log = logging.getLogger(__name__)

# One variant per way a night can end, matching the branches in night_beats().
KILL, SAVE, BLOCKED, QUIET = "kill", "save", "blocked", "quiet"
VARIANTS = (KILL, SAVE, BLOCKED, QUIET)

# Bystander slots are always available; the rest depend on the variant.
BYSTANDERS = {"a", "b", "c"}
ALLOWED: dict[str, set[str]] = {
    KILL: BYSTANDERS | {"victim", "role"},
    SAVE: BYSTANDERS | {"attacked"},
    BLOCKED: BYSTANDERS,
    QUIET: BYSTANDERS,
}

MIN_BEATS, MAX_BEATS = 3, 6

# Either a {placeholder} or a brace loose in the prose. Placeholder first, so
# `{a}` is read as one and only a genuinely orphaned brace hits group 2.
PLACEHOLDER = re.compile(r"\{([^{}]*)\}|([{}])")

SYSTEM = (
    "You are the narrator of a game of Mafia played in a Discord channel. You "
    "write tense, atmospheric, slightly pulpy small-town noir. Short sentences. "
    "Concrete detail: a gate, a kettle, a dog, a dark patch on the stones. Dry "
    "wit is welcome; jokes that break the tension are not.\n\n"
    "Hard rules:\n"
    "- Write ONLY the placeholders you are told you may use. Never invent a "
    "name, and never write a name you were not given a placeholder for.\n"
    "- Keep violence implied and bloodless. No gore, no sexual content, no "
    "slurs, no real-world people.\n"
    "- Never state or guess anybody's secret role, and never hint at who the "
    "killer is. You do not know, and the players must not think you do.\n"
    "- Players are real people whose gender you do not know. Refer to them as "
    "they/them, always, or avoid the pronoun. Never he, she, him or her.\n"
    "- Each beat is one or two short lines of prose. No bullet points, no "
    "headings, no stage directions, no 'Beat 1:' labels."
)


def _prompt(*, night: int, alive: int, dead: int, name_saved: bool) -> str:
    saved_rule = (
        "`{attacked}` is the player who was attacked and lived. Name them."
        if name_saved
        else "You may NOT name who was attacked. Use no placeholder for them: "
             "describe the rescue so the town learns only that somebody lived."
    )
    history = (
        "This is the first night; nothing has happened yet."
        if night <= 1
        else f"It is night {night}. {dead} player(s) have already died. "
             f"{alive} are left and everyone is frightened."
    )
    return (
        f"{history}\n\n"
        "Write FOUR separate versions of tonight, one for each possible ending. "
        "You do not know which will happen, so each must stand alone and must "
        f"open with its own atmosphere. Each version is {MIN_BEATS}-{MAX_BEATS} "
        "beats, posted one at a time about three seconds apart, so every beat "
        "should end on a small hook.\n\n"
        "Give each beat room: two or three sentences, 20 to 50 words, and let "
        "the last sentence land the turn. Single-line fragments read as notes "
        "toward a story rather than the story itself.\n\n"
        "Placeholders are filled in later with real player mentions:\n"
        "  {a} {b} {c} - living players with nothing to do with tonight. Use "
        "them for a red herring: somebody hears a scream, fears the worst, and "
        "it turns out to be {b} being loud. This misdirection is the best part "
        "of the job -- do it every version.\n"
        "  {victim} - the player who died. Only in \"kill\".\n"
        "  {role} - the dead player's revealed role, arriving already bold and "
        "with its own emoji. It goes at the END of the SAME beat that names "
        "{victim}, after a full stop, never as a beat of its own -- a beat "
        "containing only a role is not a sentence. Only in \"kill\".\n"
        "  {attacked} - see below.\n\n"
        "The four versions:\n"
        "  \"kill\"    - somebody was killed. Build to it: the approach, the "
        "moment, then the body found at dawn and {victim} named with {role}.\n"
        f"  \"save\"    - they went out and failed. Someone was attacked and a "
        f"healer got there first. {saved_rule}\n"
        "  \"blocked\" - nobody who moves at night managed to get out at all. "
        "Name nobody but {a}/{b}/{c}. An empty, uneasy night.\n"
        "  \"quiet\"   - nothing happened. The town waits all night for a "
        "sound that never comes, and finds that harder.\n\n"
        "Reply with one JSON object and nothing else. It has exactly four keys "
        "-- kill, save, blocked, quiet -- and each value is a flat array of "
        f"{MIN_BEATS} to {MAX_BEATS} strings, one string per beat. Never nest an "
        "array, never put a key name inside an array, and never pack several "
        "beats into one string:\n"
        '{"kill": ["first beat", "second beat", "third beat"], '
        '"save": ["first beat", "second beat", "third beat"], '
        '"blocked": ["..."], "quiet": ["..."]}'
    )


def _scrub(beat: str, allowed: set[str]) -> str:
    """
    Keep the placeholders we can fill; neutralise everything brace-shaped.

    A model that writes `{killer}` or a lone `{` would blow `format_map()` up at
    the worst possible moment. Unknown names become a vague noun, stray braces
    vanish, and the beat still reads.
    """
    def replace(match: re.Match) -> str:
        if match.group(2):  # a stray brace with no placeholder around it
            return ""
        name = match.group(1).strip()
        return "{" + name + "}" if name in allowed else "someone"

    return PLACEHOLDER.sub(replace, beat)


def _clean(payload: dict, *, name_saved: bool) -> dict[str, list[str]] | None:
    """Keep only variants that came back usable. Partial results are fine."""
    out: dict[str, list[str]] = {}
    for variant in VARIANTS:
        raw = payload.get(variant)
        if not isinstance(raw, list):
            continue
        allowed = set(ALLOWED[variant])
        if variant == SAVE and not name_saved:
            allowed.discard("attacked")  # discreet mode: strip it even if asked for
        beats = [
            _scrub(str(item).strip(), allowed)
            for item in raw[:MAX_BEATS]
            if isinstance(item, str) and item.strip()
        ]
        if len(beats) >= MIN_BEATS:
            out[variant] = beats
    return out or None


async def generate(
    bot, *, night: int, alive: int, dead: int, mode: str
) -> dict[str, list[str]] | None:
    """Ask for all four versions of tonight. Returns None if unavailable."""
    if mode == narrator.OFF or not llm.configured():
        return None

    payload = await llm.chat_json(
        bot,
        system=SYSTEM,
        user=_prompt(
            night=night, alive=alive, dead=dead,
            name_saved=(mode == narrator.DRAMATIC),
        ),
        # Four versions of a night is ~900 tokens of prose, but a reasoning
        # model bills its thinking against the same allowance and will happily
        # spend 2800 of them planning. Hence the headroom, and the low effort:
        # this is atmosphere, not a maths problem. Nothing waits on it anyway.
        max_tokens=5000,
        reasoning_effort=llm.setting("LLM_REASONING_EFFORT", "low"),
        # High enough to stop every night sounding the same, low enough that a
        # mid-size model still returns the shape it was asked for.
        temperature=0.95,
    )
    if payload is None:
        return None

    cleaned = _clean(payload, name_saved=(mode == narrator.DRAMATIC))
    if cleaned is None:
        log.warning("AI narration came back with no usable variant")
    else:
        log.info("AI narration ready for night %d: %s", night, ", ".join(cleaned))
    return cleaned


# ---------------------------------------------------------------------------
# Filling it in
# ---------------------------------------------------------------------------


class _Slots(dict):
    """format_map source that can't KeyError on a placeholder we missed."""

    def __missing__(self, key: str) -> str:
        return "someone"


def variant_for(outcome) -> str:
    if outcome.victim is not None:
        return KILL
    if outcome.rescued:
        return SAVE
    if outcome.mafia_blocked:
        return BLOCKED
    return QUIET


def fill(beats: list[str], slots: dict) -> list[str] | None:
    """Substitute real mentions. Returns None if anything is malformed."""
    source = _Slots(slots)
    try:
        return [beat.format_map(source) for beat in beats]
    except (ValueError, IndexError, AttributeError):
        log.warning("AI narration had unusable formatting; falling back")
        return None
