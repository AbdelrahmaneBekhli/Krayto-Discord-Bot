---
tags: [command, utility]
category: Utility
file: cogs/general.py
---

# /ping

Liveness check. [cogs/general.py](cogs/general.py)

No options. Replies with **one line of plain text**:

```
Pong! 🏓  🟢 connection 99ms  ·  🟡 reply 253ms
```

| Number | What it measures | Refresh |
|---|---|---|
| **connection** | Heartbeat round-trip to Discord's gateway | ~every 41s |
| **reply** | This request's REST round-trip | every invocation |

## Design: small and jargon-free

This went through two rejected versions, and both lessons are worth keeping.

**It said `Gateway` and `API`**, footed with *"Gateway = heartbeat RTT · API = this request"*. Accurate and useless — "API = this request" tells a user nothing.

**Then it was an embed**: verdict sentence, two described fields, coloured bar, footer. Correct, readable, and far too bulky for a liveness check.

> [!important] Two rules for this command
> 1. **No jargon.** `gateway`, `API`, `RTT` and `heartbeat` are internal vocabulary. User-facing text says *connection* and *reply*.
> 2. **One line, no embed.** A ping is the smallest possible answer to "are you alive". If something new seems worth adding here, it probably isn't.

What survived the cut: the coloured dot (health at a glance, costs one character) and the two plain words (which number is which).

## Health dots

`_BANDS` maps a latency to a dot — under 150ms 🟢, under 300ms 🟡, above 🔴. One tuple at the top of the file, easy to retune.

## Why connection looks frozen

`bot.latency` is **not measured when the command runs**. It's the time between the last heartbeat discord.py sent and the ACK that came back, and Discord's heartbeat interval is roughly **41 seconds**.

> [!note] Identical numbers are correct
> Several `/ping`s inside one heartbeat window all report the same figure — a cached value is being read, not a fresh measurement. If it changed every invocation, *that* would be the bug.

## How reply is measured

```python
start = time.perf_counter()
await interaction.response.send_message("Pinging…")
reply_ms = (time.perf_counter() - start) * 1000
```

Send a placeholder, measure how long Discord took to accept it, then `edit_original_response` swaps in the result. One extra HTTP call per ping, in exchange for a number that reflects what users actually feel — and unlike connection, it moves.

## Before the first heartbeat

`bot.latency` is `nan` until the first heartbeat lands. `math.isfinite()` catches `nan` and both infinities in one check; it then reads `⚪ connection starting up` rather than `nan ms`.

## Scope

Neither number touches [[Truth or Dare API]] — a different host, and the one that actually degrades the game commands. Timing it is in [[Backlog]].

Unlike the game commands, `/ping` never calls `defer()`: it responds immediately and works afterwards, so it's nowhere near the 3s budget. See [[Interaction Timing]].

## Related
- [[Bot Startup & Lifecycle]]
