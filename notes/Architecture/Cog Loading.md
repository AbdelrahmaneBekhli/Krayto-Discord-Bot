---
tags: [architecture, core]
---

# Cog Loading

## The list

[main.py](main.py) declares a module-level tuple:

```python
EXTENSIONS = (
    "cogs.general",
    "cogs.help",
    "cogs.questions.tod",
    "cogs.questions.nhie_wyr",
    "cogs.questions.paranoia",
)
```

**To add a cog:** write the module with an `async def setup(bot)` at the bottom, then add its dotted path here. Nothing else is needed — `/help` picks it up automatically via [[Help Registry]].

## Failure isolation

Each load is wrapped individually:

```python
for ext in EXTENSIONS:
    try:
        await self.load_extension(ext)
    except Exception:
        log.exception("Failed to load extension %s", ext)
    else:
        log.info("Loaded extension %s", ext)
```

A syntax error or bad import in one cog logs a traceback and the bot still starts with the rest. Previously a single bad cog aborted startup entirely.

> [!tip] Read the startup log
> Because failures are non-fatal, a missing command is easy to miss. If a slash command vanished, grep the log for `Failed to load extension`.

## Layout

```
cogs/
  __init__.py
  _help_registry.py     # not a cog — shared dataclass + collector
  general.py            # /ping
  help.py               # /help
  questions/
    __init__.py
    tod.py              # /tod
    nhie_wyr.py         # /nhie_wyr
    paranoia.py         # /paranoia
    _shared/
      __init__.py
      _config.py        # API URLs + rating choices
      _http.py          # the API client
      _base_prompt_view.py
```

Leading-underscore modules are **shared helpers, not cogs** — they have no `setup()` and must never be listed in `EXTENSIONS`.

The `__init__.py` files are present so these are real packages rather than implicit namespace packages. Imports worked without them, but explicit is sturdier.

## Related
- [[Bot Startup & Lifecycle]]
- [[Help Registry]]
