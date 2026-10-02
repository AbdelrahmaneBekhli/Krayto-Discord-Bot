---
tags: [command, game]
category: Games
file: cogs/questions/tod.py
---

# /tod

Truth or Dare with refresh buttons. [cogs/questions/tod.py](cogs/questions/tod.py)

## Options

| Option | Type | Required | Notes |
|---|---|---|---|
| `rating` | choice | no | Any / PG / PG-13 / R — see [[Truth or Dare API]] |
| `lock` | bool | no | Defaults `False`. `True` restricts buttons to you |

## Behaviour

1. Defers immediately ([[Interaction Timing]]).
2. Picks `truth` or `dare` at random for the opening prompt.
3. Sends an embed plus a `TODView`.

## Buttons

| Label | Style | Fetches |
|---|---|---|
| ✅ Truth | green | `/api/truth` |
| 🔥 Dare | red | `/api/dare` |
| 🎲 Random | blurple | either, at random |

Each press re-fetches and edits the **same** message. Embed colour tracks the kind: green for truth, red for dare. View expires after 180s — see [[Base Prompt View]].

## Examples

```
/tod
/tod rating:PG lock:true
```

## Notes

- `KINDS = ("truth", "dare")` is the single source of truth for the random pick.
- `lock` is a plain `bool = False`. It used to be `bool | None = None` tested with `lock is True` — a pointless third state.

## Related
- [[nhie_wyr]] · [[paranoia]] — same pattern
