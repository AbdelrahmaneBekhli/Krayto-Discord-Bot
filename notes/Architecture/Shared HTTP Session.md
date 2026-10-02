---
tags: [architecture, http]
---

# Shared HTTP Session

## One session for the whole bot

Created once in `setup_hook` ([main.py](main.py)):

```python
self.session = aiohttp.ClientSession(
    timeout=aiohttp.ClientTimeout(total=10),
    headers={"User-Agent": "DiscordBot (truthordarebot.xyz)"},
)
```

Why not in `__init__`? `ClientSession` binds to the running event loop. Built in `__init__` there is no loop yet, so you get a session attached to the wrong loop (or a `DeprecationWarning` then a hang). `setup_hook` runs inside the loop, which is correct.

Cogs reach it as `self.bot.session` and must **never** create their own — one connection pool is the point.

## The client: `api_get`

[cogs/questions/_shared/_http.py](cogs/questions/_shared/_http.py)

```python
async def api_get(bot, base: str, path: str, rating: str | None = None) -> dict
```

**Contract: it never raises for network or API problems.** It always returns a `dict` — either the decoded payload, or `{"_error": "<user-facing message>"}`.

This matters because callers are button callbacks. An exception there surfaces as a silent "interaction failed" with the message stuck in a deferred state.

The one case it *does* raise is `RuntimeError` when `bot.session` is missing or closed — that's a programming error, not a runtime condition.

### Failure handling

| Condition | Result |
|---|---|
| HTTP 429 with `Retry-After` | `⏳ Rate-limited. Try again in {n}s.` |
| HTTP 429 without the header | `⏳ Rate-limited. Try again in a few seconds.` |
| Any HTTP ≥ 400 | `⚠️ API error (HTTP {status}). Try again shortly.` |
| `asyncio.TimeoutError` | `⏳ The question API timed out. Try again.` |
| `aiohttp.ClientError` | `⚠️ Couldn't reach the question API...` |
| Body isn't JSON (`ValueError`) | `⚠️ API returned an unexpected response.` |
| Body is JSON but not an object | same as above |

`resp.json(content_type=None)` is used so a wrong `Content-Type` header doesn't turn a perfectly good body into an exception.

## Reading the result

Never touch `data["question"]` directly. Use the helpers:

```python
prompt_text(data) -> str   # error message, the question, or "No prompt found."
is_error(data) -> bool     # was this an error result?
```

`prompt_text` also treats a whitespace-only question as missing. Keeping errors under a separate `_error` key means an error can never be mistaken for real question content — which is exactly what the earlier version did by stuffing error strings into `"question"`.

## Rating parameter

`_params_with_rating` omits the query param entirely when rating is `None` or `"any"`, otherwise sends `?rating=<value>`. See [[Truth or Dare API]] for accepted values.

## Related
- [[Truth or Dare API]]
- [[Base Prompt View]]
- [[Interaction Timing]]
