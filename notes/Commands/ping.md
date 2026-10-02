---
tags: [command, utility]
category: Utility
file: cogs/general.py
---

# /ping

Liveness check. [cogs/general.py](cogs/general.py)

No options. Replies with an embed: a plain-English verdict, then two numbers.

| Field | What it measures | Refresh |
|---|---|---|
| **Connection** | Heartbeat round-trip to Discord's gateway | ~every 41s |
| **Reply speed** | This request's REST round-trip | every invocation |

## Wording is deliberately non-technical

The fields used to read `Gateway` and `API`, footed with *"Gateway = heartbeat RTT · API = this request"*. That's accurate and useless — "API = this request" tells a user nothing.

> [!important] Keep the user-facing text jargon-free
> `Gateway`, `API`, `RTT` and `heartbeat` are all internal vocabulary. The embed says **Connection** ("My link to Discord") and **Reply speed** ("How long this reply took"). Keep it that way if you edit this command.

## Health bands

`_BANDS` maps a latency to an emoji, a word and a colour:

| Under | Shows | Reads |
|---|---|---|
| 150ms | 🟢 | great |
| 300ms | 🟡 | okay |
| — | 🔴 | a bit slow |

Each field gets its own dot. The verdict line and the embed colour follow **whichever number is worse**, so one bad reading can't be hidden by a good one. Thresholds are a single tuple at the top of the file — easy to retune.

## Why Connection looks frozen

`bot.latency` is **not measured when the command runs**. It's the time between the last heartbeat discord.py sent and the ACK that came back, and Discord's heartbeat interval is roughly **41 seconds**.

> [!note] Identical numbers are correct
> Several `/ping`s inside one heartbeat window all report the same figure — a cached value is being read, not a fresh measurement. If it changed every invocation, *that* would be the bug. The footer says this in user terms.

## How Reply speed is measured

```python
start = time.perf_counter()
await interaction.response.send_message("Pinging…")
reply_ms = (time.perf_counter() - start) * 1000
```

Send a placeholder, measure how long Discord took to accept it, then `edit_original_response` swaps in the embed. One extra HTTP call per ping, in exchange for a number that reflects what users actually feel — and unlike Connection, it moves.

## Before the first heartbeat

`bot.latency` is `nan` until the first heartbeat lands. `math.isfinite()` catches `nan` and both infinities in one check; Connection then shows ⚪ **"starting up…"** rather than `nan ms` or a bare dash.

## Scope

Neither number touches [[Truth or Dare API]] — a different host entirely, and the one that actually degrades the game commands. Timing it is in [[Backlog]].

Unlike the game commands, `/ping` never calls `defer()`: it responds immediately and works afterwards, so it's nowhere near the 3s budget. See [[Interaction Timing]].

## Related
- [[Bot Startup & Lifecycle]]
