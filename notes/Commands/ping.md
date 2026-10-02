---
tags: [command, utility]
category: Utility
file: cogs/general.py
---

# /ping

Liveness check. [cogs/general.py](cogs/general.py)

No options. Replies with an embed showing **two different** measurements:

| Field | What it measures | Refresh |
|---|---|---|
| **Gateway** | Heartbeat round-trip to Discord's gateway | ~every 41s |
| **API** | This request's REST round-trip | every invocation |

## Why Gateway looks frozen

`bot.latency` is **not measured when the command runs**. It's the time between the last heartbeat discord.py sent and the ACK that came back. Discord sets the heartbeat interval at roughly **41 seconds**, so the value only refreshes about once a minute.

> [!note] Identical numbers are correct
> Several `/ping`s inside one heartbeat window all report the same figure — it's a cached value being read, not a fresh measurement. If it changed on every invocation, *that* would be the bug.

## How API is measured

```python
start = time.perf_counter()
await interaction.response.send_message("Pinging…")
api = time.perf_counter() - start
```

Send first, measure how long Discord took to accept it, then `edit_original_response` to swap the placeholder for the embed. This costs one extra HTTP call per ping — the reason it's worth it is that this is the number users actually feel, and unlike Gateway it moves.

## Non-finite guard

`bot.latency` is `nan` until the first heartbeat completes. `_format_latency()` uses `math.isfinite()`, which rejects `nan` and both infinities in one check, rendering `—` instead of `nan ms`.

## Scope

Neither number says anything about [[Truth or Dare API]] — that's a different host entirely. Timing it instead is in [[Backlog]].

Unlike the game commands, `/ping` never calls `defer()`: it responds immediately and does its work afterwards, so it's nowhere near the 3s budget. See [[Interaction Timing]].

## Related
- [[Bot Startup & Lifecycle]]
