---
tags: [architecture]
---

# Help Registry

[cogs/_help_registry.py](cogs/_help_registry.py) — a shared dataclass, **not a cog**. Consumed by [[help]].

## `HelpEntry`

```python
@dataclass(frozen=True)
class HelpEntry:
    name: str                  # slash command name, no '/'
    summary: str               # one line
    category: str              # "Games", "Utility", "Admin", ...
    examples: List[str]
    show_in_help: bool = True  # False hides it from /help entirely
    public: bool = True        # reserved, currently unused
    options_help: Dict[str, str] = field(default_factory=dict)
```

Each cog declares a **class-level** `HELP_ENTRIES` list. `options_help` maps an option name to override text; anything not listed falls back to the `app_commands.describe` description.

## Collection

```python
get_help_entries(bot)  # walks bot.cogs.values(), extends from each HELP_ENTRIES
by_name(entries)       # -> {name: HelpEntry}
```

Discovery is duck-typed via `getattr(cog, "HELP_ENTRIES", None)`, so a cog without it is simply skipped — no registration step, no base class.

## Two sources, merged

[[help]] combines:

1. **Metadata** — `HELP_ENTRIES`, used for category grouping and examples.
2. **Live tree** — `bot.tree.get_commands()`, the commands actually registered.

A command with no metadata still appears, under a fallback **Other** category using its Discord description. So a new cog is never invisible, it's just less nicely presented.

## Hiding a command

Set `show_in_help=False`. [[help]] then excludes it from the index, from autocomplete, **and** answers `/help <that-name>` with "I couldn't find it".

> [!bug] This was a real leak
> A deleted private cog had no `HELP_ENTRIES` at all, so the *fallback* path listed it to everyone under **Other** with its description. Opting out of help requires an explicit entry with `show_in_help=False` — omitting metadata does the opposite of hiding.

## Caveat

`frozen=True` generates `__hash__`, but the `List`/`Dict` fields are unhashable — so hashing a `HelpEntry` raises `TypeError`. Nothing does, but don't put them in a `set` or use one as a dict key.

## Related
- [[help]]
- [[Cog Loading]]
