---
tags: [command, game]
category: Games
file: cogs/questions/nhie_wyr.py
---

# /nhie_wyr

Never Have I Ever + Would You Rather in one command. [cogs/questions/nhie_wyr.py](cogs/questions/nhie_wyr.py)

## Options

| Option | Type | Required | Notes |
|---|---|---|---|
| `rating` | choice | no | Any / PG / PG-13 / R |
| `lock` | bool | no | Defaults `False` |

## Buttons

| Label | Style | Fetches |
|---|---|---|
| 🙋 NHIE | green | `/api/nhie` |
| 🤔 WYR | blurple | `/api/wyr` |
| 🎲 Random | grey | either |

## Titles

A `TITLES` dict maps the short kind to the display name:

```python
TITLES = {"nhie": "Never Have I Ever", "wyr": "Would You Rather"}
```

This replaced an inline `"Never Have I Ever" if kind == "nhie" else "Would You Rather"` ternary, which would silently mislabel any third kind as WYR. `TITLES.get(kind, kind.upper())` degrades honestly instead.

## Examples

```
/nhie_wyr
/nhie_wyr rating:Any
/nhie_wyr rating:PG lock:true
```

## Note on the name

The underscore in `nhie_wyr` is legal for slash commands (lowercase, no spaces). Splitting into `/nhie` and `/wyr` is in [[Backlog]].

## Related
- [[tod]] · [[paranoia]]
