---
tags: [moc]
---

# Discord Bot — Home

Vault for the Truth-or-Dare style Discord bot in this repo. The vault **is** the repo root, so these notes are versioned next to the code they describe.

> [!tip] Keep notes honest
> Every note links to real files as `path:line`. If you move code, search the vault for the old path.

## Architecture
- [[Bot Startup & Lifecycle]] — token loading, `setup_hook`, shutdown
- [[Cog Loading]] — the `EXTENSIONS` tuple and per-cog failure isolation
- [[Shared HTTP Session]] — the one `aiohttp` session and its error contract
- [[Base Prompt View]] — buttons, the owner lock, timeouts
- [[Help Registry]] — how `/help` discovers commands
- [[Game Framework]] — lobby, per-channel registry, the button-to-ephemeral rule
- [[Truth or Dare API]] — the upstream API contract

## Commands
- Prompts: [[tod]] · [[nhie_wyr]] · [[paranoia]]
- Party games: [[mafia]] · [[wavelength]]
- Utility: [[help]] · [[ping]]

## Planning
- [[Backlog]] — ideas, ranked
- [[Known Gaps]] — accepted weaknesses and traps
- [[Changelog]] — what actually shipped

## Stack
| Thing | Version |
|---|---|
| Python | 3.12.8 |
| discord.py | 2.7.1 |
| aiohttp | 3.13.2 |

Entry point is [main.py](main.py). Dependencies pinned in [requirements.txt](requirements.txt).

## Conventions
- Slash commands only — no message-content intent, no prefix commands.
- Anything that makes a network call **defers the interaction first**. See [[Interaction Timing]].
- Anything private goes **button → ephemeral**, never a DM. See [[Game Framework]].
- Cogs never build their own HTTP session; they use `bot.session`.
