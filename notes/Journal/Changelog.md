---
tags: [journal, changelog]
---

# Changelog

Newest first. Only things that actually shipped — plans live in [[Backlog]].

## 2026-10-02 — Two party games

### Added
- **[[mafia]]** — full social deduction game. Host configures how many Mafia,
  Detective, Doctor and Police; everyone else is a Villager. Night/day/vote
  loop, plurality voting with ties eliminating nobody, win on wipeout or parity.
  Police is **detain** (roleblock + save) so it isn't a second Detective.
- **[[wavelength]]** — a Psychic gets a secret spot 1–10 on a spectrum and gives
  one clue; everyone else guesses. 45 spectrums, drawn without replacement. The
  Psychic scores the average of their guessers, so a clue that works on the
  whole room beats a clue that works on one friend.
- **[[Game Framework]]** — shared lobby view and a one-game-per-channel registry.

### Decisions
- **No DMs.** Every private moment is a button that replies ephemerally. DMs fail
  silently when closed and would stall a game with no visible cause. The one DM
  is the Detective's result, which must outlive the phase change — and it falls
  back to the **My role** button.
- Rules engines take and return plain data, no Discord objects, so they're
  testable headlessly. 38 assertions plus 200 simulated games, all passing.

### Fixed before shipping
- Night resolution stored Doctor/Police targets as flat sets, losing who acted —
  with two Doctors, detaining one cancelled both saves. Now keyed by actor.

## 2026-10-02 — Audit, hardening, dependency bump

Session notes: [[2026-10-02]]

### Changed
- **discord.py 2.6.4 → 2.7.1.** No breaking changes affected this code; all cogs verified loading on the new version. `aiohttp` 3.13.2.
- Added `requirements.txt` with pins, and `.env.example` (`.gitignore` already whitelisted one that didn't exist).
- Added `__init__.py` to `cogs/questions/` and `cogs/questions/_shared/` — real packages instead of implicit namespace packages.

### Fixed
- **Interaction timing.** `/tod`, `/nhie_wyr` and `/paranoia` each hit the API *before* responding. With a 10s client timeout against Discord's 3s limit, a slow upstream meant `404 Unknown interaction` and "the application did not respond". All three now defer first. Most serious bug found. → [[Interaction Timing]]
- **Dead `.env` support.** `main.py` raised "Put it in .env" but nothing read a `.env`, and `python-dotenv` wasn't installed — the bot only started if the env var was set by hand. Now resolves env → `.env` → `tokens.txt` with no new dependency. → [[Bot Startup & Lifecycle]]
- **Unhandled network errors.** The API client only handled 429. A timeout, DNS failure or 5xx raised straight out of a button callback, leaving the message stuck deferred with no feedback. Now covers timeouts, `ClientError`, bad JSON, non-dict bodies and all 4xx/5xx, each with its own message, and honours `Retry-After`. → [[Shared HTTP Session]]
- **Windows console crash.** `print(f"✅ Logged in as ...")` raises `UnicodeEncodeError` on a `cp1252` console. Replaced with `discord.utils.setup_logging()`.
- **`/help` could exceed Discord limits.** Embed field values cap at 1024 chars; enough commands would raise `HTTPException`. Added `_fit_field()`.
- **`/help` leaked hidden commands.** Entries with `show_in_help=False` still rendered in detail view. → [[Help Registry]]
- **One bad cog killed startup.** Each extension now loads independently and logs its own failure. → [[Cog Loading]]

### Improved
- Owner lock moved from a manual `guard()` call into `View.interaction_check`, so a new button can't forget it. → [[Base Prompt View]]
- Added `on_error` to the view base — exceptions now tell the user instead of failing silently.
- `on_timeout` catches any `HTTPException` (was `NotFound` only) and calls `stop()`.
- `/help` command argument gained autocomplete.
- `/ping` reports gateway latency, NaN-safe before the first heartbeat. → [[ping]]
- `lock` is now `bool = False` instead of a three-state `bool | None = None`.
- Per-type embed colours.
- Errors no longer masquerade as question content — separate `_error` key read via `prompt_text()`.

### Removed
- `cogs/rana.py` — a private `/bloom` command flow. Note: it had no `HELP_ENTRIES`, so the `/help` fallback path was listing it publicly under **Other**.

### Verified
All cogs load, 5 slash commands register, live calls to all 5 API endpoints succeed across every rating, and all 9 HTTP failure modes return clean messages. Confirmed `tokens.txt` was never tracked by git.

### Also
Set up this vault. → [[Vault Guide]]
