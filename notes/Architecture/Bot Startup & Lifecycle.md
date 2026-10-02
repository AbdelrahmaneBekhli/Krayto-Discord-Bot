---
tags: [architecture, core]
---

# Bot Startup & Lifecycle

Everything lives in [main.py](main.py). `MyBot` subclasses `commands.Bot`.

## 1. Token resolution

`load_token()` tries three sources **in order** and uses the first that yields a value:

1. `DISCORD_TOKEN` environment variable
2. `.env` next to `main.py` — parsed as `KEY=VALUE`
3. `tokens.txt` next to `main.py` — accepts a bare token on its own line

`_read_token_file()` handles both shapes: it skips blanks and `#` comments, and for a `KEY=VALUE` line only accepts the keys `DISCORD_TOKEN`, `TOKEN` or `BOT_TOKEN`. It reads as `utf-8-sig` so a BOM from Notepad doesn't corrupt the first character.

If all three miss, it raises `RuntimeError` with instructions. There is **no `python-dotenv` dependency** — this is deliberate, the parser is ~15 lines.

> [!warning] Never commit the token
> `tokens.txt` and `.env` are both in `.gitignore`. `.env.example` is whitelisted as the template. Confirmed untracked — keep it that way.

## 2. Construction

```python
super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default())
```

- `Intents.default()` is enough because the bot is slash-command only. It does **not** need the privileged message-content intent.
- `command_prefix` is effectively unused but must be valid; `when_mentioned` is the harmless choice.
- `self.session` is declared `None` here and created in `setup_hook` — see [[Shared HTTP Session]] for why it can't be made in `__init__`.

## 3. `setup_hook`

Runs once, after login but before the first `on_ready`. In order:

1. Create the shared `aiohttp.ClientSession`.
2. Load every extension in `EXTENSIONS` — see [[Cog Loading]].
3. `await self.tree.sync()` and log how many commands registered.

> [!note] Global sync on every boot
> `tree.sync()` with no `guild=` syncs **globally**, which Discord may take up to an hour to propagate. It also runs on every single start. Fine at this scale; see [[Known Gaps]] if that ever becomes annoying.

## 4. Shutdown

`close()` is overridden to close the HTTP session *before* delegating to `super().close()`. Without this you get aiohttp's "Unclosed client session" warning on exit.

## 5. Logging

`main()` calls `discord.utils.setup_logging(level=logging.INFO)` and then passes `log_handler=None` to `bot.run()` so discord.py doesn't install a second handler and double-log every line.

> [!bug] Why there are no emoji in log output
> The original code did `print(f"✅ Logged in as {self.user}")`. On a Windows `cp1252` console that raises `UnicodeEncodeError` and takes down the handler. Log messages are plain ASCII now. Emoji are fine in strings sent *to Discord* — just not to stdout.

## Related
- [[Cog Loading]]
- [[Shared HTTP Session]]
- [[Interaction Timing]]
