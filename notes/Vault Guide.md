---
tags: [meta]
---

# Vault Guide

How this vault is set up. Start at [[Home]].

## The vault is the repo

The vault root **is** the project folder, so notes are versioned in git next to the code. A note can point at `cogs/questions/tod.py` and that path stays valid for anyone who clones the repo.

In Obsidian: **Open folder as vault** → `C:\Users\abdel\Documents\Discord Bot app`. It becomes a second vault alongside your existing `Obsidian Vault`; switch with the vault icon in the bottom-left.

## Why one vault, not four

Vaults are isolated — `[[wikilinks]]`, backlinks, graph, search and tags do not cross vault boundaries. Four vaults would mean [[tod]] could never link to [[Truth or Dare API]], which is most of the value. One vault, four folders gives the separation without losing the links.

```
notes/
├── Home.md              ← dashboard, start here
├── Vault Guide.md       ← this note
├── Plugin Setup.md
├── Architecture/        ← how the bot works
├── Commands/            ← one note per slash command
├── Roadmap/             ← Backlog, Known Gaps
├── Journal/             ← Changelog + daily notes
└── Templates/           ← [[Daily Dev Note]]
```

## Configured for you

| Setting | Value |
|---|---|
| New notes | `notes/` |
| Attachments | `notes/_attachments` |
| Link format | Shortest path, wikilinks |
| Daily notes | `notes/Journal/YYYY-MM-DD`, using [[Daily Dev Note]] |
| Templates | `notes/Templates` |
| Accent colour | Discord blurple `#5865F2` |
| Graph colours | Architecture blue · Commands green · Roadmap amber · Journal purple |

> [!important] `.venv/`, `.git/` and `__pycache__/` are excluded
> Via `userIgnoreFilters` in `.obsidian/app.json`. Without this, search and quick-switcher get polluted by thousands of dependency files. If you add a build or cache directory, add it there too.

## Conventions

- **Link generously.** A note nobody links to is a note you'll never find again.
- **Reference code as a path**, `cogs/help.py` or `main.py:42`, never pasted code blocks you'd have to maintain twice.
- **Callouts carry weight:** `> [!danger]` for a trap that bites, `> [!bug]` for a bug that actually happened, `> [!note]` for context.
- **Decisions beat descriptions.** The code already says *what*. Notes exist for *why*, and for what was tried and rejected.
- **[[Known Gaps]] is for accepted problems.** Writing a weakness down beats rediscovering it in six months.

## Routine

- Starting a session → open [[Home]], skim [[Backlog]]
- During → jot in today's daily note (`Ctrl+P` → "Open today's daily note")
- Shipping something → move the item to **Done** in [[Backlog]], add a line to [[Changelog]]
- Changing how something works → update the matching [[Architecture/Bot Startup & Lifecycle|Architecture]] note in the same commit

## Git

`.obsidian/` config is committed so the setup travels with the repo. `.obsidian/workspace.json` is **ignored** — it's per-machine pane layout and would conflict constantly.

## Related
- [[Plugin Setup]] · [[Home]]
