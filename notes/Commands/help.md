---
tags: [command, utility]
category: Utility
file: cogs/help.py
---

# /help

Self-documenting command index, driven by [[Help Registry]]. [cogs/help.py](cogs/help.py)

## Options

| Option | Type | Required | Notes |
|---|---|---|---|
| `command` | string | no | With autocomplete. Leading `/` is tolerated |

Always replies **ephemerally** — help never clutters the channel.

## Two modes

**Index** (no argument) — groups commands by category in a fixed order: `Games`, `Utility`, `Admin`, `Other`, then any remaining categories alphabetically. Commands lacking metadata land in `Other`.

**Detail** (`/help tod`) — summary, examples, and an auto-generated options list read from the live command's `parameters`. Per-option text prefers `options_help`, falling back to the Discord description. Choice lists are appended automatically, but only when `options_help` hasn't overridden that option.

## Autocomplete

`_command_autocomplete` offers `_visible_names()` — metadata entries with `show_in_help=True`, plus live tree commands lacking metadata — filtered by substring, sorted, capped at Discord's 25.

## Guards

- **Hidden commands**: `show_in_help=False` → excluded from the index, from autocomplete, and `/help <name>` reports not-found. See the leak note in [[Help Registry]].
- **Field limits**: `_fit_field()` packs lines into Discord's 1024-char field cap, appending `…` when it has to stop. Enough commands or long examples would otherwise raise `HTTPException`.

> [!tip] Nothing to update here when adding a command
> Add `HELP_ENTRIES` to the new cog. `/help` discovers it. If you forget, it still shows up under `Other`.

## Related
- [[Help Registry]]
