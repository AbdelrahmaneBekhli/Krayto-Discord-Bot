---
tags: [roadmap, board]
---

# Backlog

Checkboxes + `#next` / `#someday` tags. Click a tag in the tag pane to filter, or use the Tasks plugin ([[Plugin Setup]]) to query across the vault.

## Next

- [ ] Split `/nhie_wyr` into `/nhie` and `/wyr` #next
      Discoverability — nobody types an underscore. Keep the combined view's buttons.
- [ ] Guild-scoped sync for development #next
      `tree.sync(guild=...)` propagates instantly vs. up to an hour globally. Gate on a `DEV_GUILD_ID` env var. See [[Bot Startup & Lifecycle]].
- [ ] Persistent views #next
      `timeout=None` + `custom_id` + `bot.add_view()` so buttons survive a restart. See [[Known Gaps]].
- [ ] Per-user cooldown on game commands #next
      `@app_commands.checks.cooldown(1, 3.0)` — protects our 429 budget on [[Truth or Dare API]].

## Soon

- [ ] `/tod` Truth-only and Dare-only variants
- [ ] Rating lock per channel, so a server can cap at PG
- [ ] Show the question `id` in the embed footer — makes reporting a bad question possible
- [ ] Language option from the API's `translations` field (bn/de/es/fr/hi/tl already in every response)
- [ ] Retry once on a timeout before surfacing an error
- [ ] Report question-API latency in `/ping`
      Gateway and REST timings are in; the third host that actually degrades the game commands isn't measured. See [[ping]].

## Someday

- [ ] Real Paranoia flow — whisper to one player, coin-flip the reveal #someday
      Needs per-channel state and DM permissions. See [[paranoia]].
- [ ] Local question packs as a fallback when the API is down #someday
- [ ] Scoreboard / stats — needs persistence, probably SQLite #someday
- [ ] `/help` category pagination if the command list outgrows one embed #someday

## Done

- [x] Upgrade to discord.py 2.7.1
- [x] Defer before API calls ([[Interaction Timing]])
- [x] Harden the API client ([[Shared HTTP Session]])
- [x] Autocomplete on `/help`
- [x] Pin dependencies in `requirements.txt`

## Related
- [[Known Gaps]] · [[Changelog]]
