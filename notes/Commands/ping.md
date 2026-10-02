---
tags: [command, utility]
category: Utility
file: cogs/general.py
---

# /ping

Liveness check. [cogs/general.py](cogs/general.py)

No options. Replies `Pong! 🏓 (42ms)`.

The number is `bot.latency` — the **gateway heartbeat** round-trip, not the time to handle your command. It does not measure the [[Truth or Dare API]].

## NaN guard

`bot.latency` is `nan` until the first heartbeat completes. `nan != nan` is `True` in IEEE 754, which is how the check detects it:

```python
if latency != latency or latency in (float("inf"), float("-inf")):
    suffix = ""
```

So a very early `/ping` says `Pong! 🏓` with no number rather than `nan ms`.

Responds directly with no `defer()` — it makes no network calls, so it's comfortably inside the 3s budget ([[Interaction Timing]]).

## Related
- [[Bot Startup & Lifecycle]]
