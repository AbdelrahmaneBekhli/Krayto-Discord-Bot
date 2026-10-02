---
tags: [meta]
---

# Plugin Setup

Core plugins are already enabled in `.obsidian/core-plugins.json`. Community plugins need installing by hand — **Settings → Community plugins → Browse**.

> [!note] Nothing here is required
> The vault works fully without any community plugin. These earn their place for *this* project specifically.

## Core, already on

| Plugin | Why it matters here |
|---|---|
| **Graph view** | Colour-grouped by folder. Shows which [[Architecture/Cog Loading\|Architecture]] notes a command depends on. |
| **Backlinks** | Open [[Interaction Timing]] and see every command that must obey it. |
| **Outgoing links** | Catches links I wrote to notes that don't exist yet. |
| **Tag pane** | `#next`, `#someday`, `#gotcha`, `#risk`. |
| **Daily notes** | Wired to the Daily Dev Note template. |
| **Templates** | `notes/Templates`. |
| **Properties** | Reads the YAML frontmatter on each note. |
| **Bases** | Your Obsidian supports it — see below. |

## Worth installing

### Tasks
Query checkboxes across the whole vault. [[Backlog]] is written to suit it:

````markdown
```tasks
not done
tag includes #next
path includes Roadmap
```
````

### Kanban
Turns [[Backlog]] into drag-and-drop columns. Best if you prefer a board to a list — it does rewrite the file's format, so decide before investing in the checkbox style.

### Dataview
Cross-cutting queries off the frontmatter. Every command note carries `category:` and `file:`:

````markdown
```dataview
TABLE category AS "Category", file AS "Source"
FROM #command
SORT file.name ASC
```
````

### Git
Auto-commits the vault on a timer. **Think before enabling** — this repo holds code, not just notes, so a timed auto-commit would sweep up half-finished Python into commits you didn't intend. Either skip it, or set it to notify rather than commit.

## Bases instead of Dataview

Your Obsidian has `bases` enabled, which gives you database-style views over frontmatter natively. The command notes are structured for it — `tags`, `category`, `file`. Try a base over `notes/Commands` before adding Dataview; one less plugin.

## Not worth it here
- **Excalidraw** — the graph view covers a project this size.
- **Calendar** — one daily note folder doesn't need it.
- **Spaced repetition** — this is reference material, not study material.

## Related
- [[Vault Guide]] · [[Home]]
