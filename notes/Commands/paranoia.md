---
tags: [command, game]
category: Games
file: cogs/questions/paranoia.py
---

# /paranoia

Paranoia questions with a single refresh button. [cogs/questions/paranoia.py](cogs/questions/paranoia.py)

## Options

| Option | Type | Required | Notes |
|---|---|---|---|
| `rating` | choice | no | Any / PG / PG-13 / R |
| `lock` | bool | no | Defaults `False` |

## Buttons

| Label | Style | Fetches |
|---|---|---|
| 🔁 Another | blurple | `/api/paranoia` |

Purple embed. Simplest of the three — one endpoint, one button, so `ParanoiaView` holds the button callback directly instead of a `_handle` indirection.

## Examples

```
/paranoia
/paranoia rating:PG
/paranoia lock:true
```

> [!note] Not the real party game
> This only serves the *question*. Actual Paranoia — whisper the question to one person, they answer aloud, a coin flip decides whether the question is revealed — would need per-channel state and DMs. See [[Backlog]].

## Related
- [[tod]] · [[nhie_wyr]]
