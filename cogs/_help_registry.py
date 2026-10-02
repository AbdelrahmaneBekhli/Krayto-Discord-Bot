from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict

@dataclass(frozen=True)
class HelpEntry:
    name: str                 # slash command name without '/'
    summary: str              # one-line description, used on the /help index
    category: str             # "Games", "Utility", etc.
    examples: List[str]       # example invocations
    show_in_help: bool = True # hide from public /help
    public: bool = True       # if False, show only in "private" help mode (optional)
    options_help: Dict[str, str] = field(default_factory=dict)
    # Longer "how this works" body, shown only by `/help <name>`. Markdown is
    # fine; it renders in the embed description, so it has room to breathe.
    details: str = ""


def get_help_entries(bot) -> List[HelpEntry]:
    """
    Collect help entries from all loaded cogs that define `HELP_ENTRIES`.
    """
    entries: List[HelpEntry] = []
    for cog in bot.cogs.values():
        items = getattr(cog, "HELP_ENTRIES", None)
        if items:
            entries.extend(items)
    return entries

def by_name(entries: List[HelpEntry]) -> Dict[str, HelpEntry]:
    return {e.name: e for e in entries}
