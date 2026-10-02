---
tags: [architecture, external]
---

# Truth or Dare API

Upstream public API behind [[tod]], [[nhie_wyr]] and [[paranoia]]. Config in [cogs/questions/_shared/_config.py](cogs/questions/_shared/_config.py).

```python
API_ROOT = "https://api.truthordarebot.xyz"
API_V1   = f"{API_ROOT}/v1"     # works, but unused
API_API  = f"{API_ROOT}/api"    # what the cogs use
```

## Endpoints

All `GET`, all under `/api`:

| Path | Used by |
|---|---|
| `/truth` | [[tod]] |
| `/dare` | [[tod]] |
| `/nhie` | [[nhie_wyr]] |
| `/wyr` | [[nhie_wyr]] |
| `/paranoia` | [[paranoia]] |

## Response shape

```json
{
  "translations": { "bn": "...", "de": "...", "es": "...", "fr": "...", "hi": "...", "tl": "..." },
  "id": "l3wa5hey194e",
  "type": "TRUTH",
  "rating": "PG13",
  "question": "What could make you get back together with your ex?",
  "pack": null
}
```

Only `question` is read. The other fields are available if ever wanted — `translations` could power a language option ([[Backlog]]).

> [!note] There is no `dare` key
> Every endpoint returns its text under `question`, including `/dare`. The old code did `data.get("question") or data.get("dare")` — the second half was dead. Verified against the live API.

## Rating

Sent as `?rating=<value>`, omitted entirely for `any`.

`RATING_CHOICES` in `_config.py`:

| Label | Value sent |
|---|---|
| Any | *(omitted)* |
| PG | `pg` |
| PG-13 | `pg13` |
| R | `r` |

Matching is **case-insensitive** upstream — `pg` and `PG13` both verified working, each echoing the normalised rating back in the response.

## Behaviour notes

- Unknown endpoint → **HTTP 400** (not 404). Handled by the generic `>= 400` branch in [[Shared HTTP Session]].
- No auth, no API key.
- A `User-Agent` is sent from the shared session as a courtesy.
- Rate limiting exists; 429 handling respects `Retry-After`.

> [!warning] Third-party dependency
> Not ours. If it goes down or changes shape, all three game commands degrade to error embeds. `api_get` is written so this is a graceful message, never a crash.

## Related
- [[Shared HTTP Session]]
