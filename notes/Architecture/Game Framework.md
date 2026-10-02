---
tags: [architecture, games]
---

# Game Framework

Shared scaffolding under `cogs/games/_shared/`, used by [[mafia]] and [[wavelength]]. Deliberately thin — two games isn't enough evidence to abstract hard.

## Registry — one game per channel

[cogs/games/_shared/_core.py](cogs/games/_shared/_core.py) keeps a module-level `dict[channel_id, BaseGame]`.

```python
active_game(channel_id)  # None if free
register(game)
unregister(channel_id)
```

Every game command checks it first and refuses with *"There's already a **Mafia** game running in this channel."* Without this, two lobbies in one channel would interleave their messages into nonsense.

`BaseGame.finish()` unregisters and sets `finished`. **Every exit path must reach it** — win, cancel, or lobby timeout — or that channel is locked out until the bot restarts.

## `BaseGame`

Holds only what both games share: `channel`, `host`, an ordered `players` dict (join order = stable seat order), `message`, and the `started` / `finished` flags. Plus `add_player` / `remove_player`, which return a user-facing error string or `None`.

Phases, roles and scoring live in the subclass. There's no shared phase machine — Mafia's night/day/vote loop and Wavelength's round rotation have almost nothing in common, and forcing one would cost more than it saves.

## `LobbyView`

[cogs/games/_shared/_lobby.py](cogs/games/_shared/_lobby.py) — Join / Leave / *(Setup)* / Start / Cancel, all on one row so the lobby stays small. The Setup button is removed at construction when a game doesn't pass `on_setup`, which is how Wavelength gets a 4-button lobby and Mafia a 5-button one from the same class.

Host-only on Start, Setup and Cancel. Timeout unregisters the game if it never started.

## The pattern: button → ephemeral

**No DMs anywhere.** Every private moment — your Mafia role, your night action, your Wavelength spot, your vote — is a public button that replies ephemerally.

> [!important] This is the single most important UX decision in both games
> DMs fail silently when a user has them closed or shares no mutual server setting. Mid-game, that stalls everything with no visible cause and no recovery. Ephemeral replies always work, need no setup, and vanish on their own.

The only DM is the Detective's result, because it has to outlive the phase change — and it's wrapped in `try/except discord.HTTPException` with **My role** as the fallback.

## One live message per phase

Each phase owns one channel message that gets edited in place — counters like `2/3 night actions in` update live. New phases send a new message so the history reads as a log.

Every `message.edit` is wrapped in `try/except discord.HTTPException`: the message may be deleted mid-game, and a failed cosmetic refresh must never kill a round.

## Hard limits worth remembering

| Limit | Value | Consequence |
|---|---|---|
| Select options | 25 | `max_players` is 25 |
| Buttons per row | 5 | Lobby is exactly full |
| Rows per view | 5 | Mafia's Setup uses 4 selects |
| Modal opening | Needs a fresh interaction | See the detour in [[wavelength]] |

## Testing

The rules engines are plain Python with no Discord objects — `resolve_night`, `vote_result`, `winner`, `score_for`, `Settings.validate` all take and return data. That's what let 38 assertions plus 200 simulated games run headlessly with a two-attribute fake member.

> [!tip] Keep the rules free of Discord types
> Views should read state and render it. Anything that decides an outcome belongs on the game class, where it can be tested without a gateway connection.

## Related
- [[mafia]] · [[wavelength]] · [[Known Gaps]]
