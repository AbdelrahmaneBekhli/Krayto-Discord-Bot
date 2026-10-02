---
tags: [roadmap, risk]
---

# Known Gaps

Accepted weaknesses. Each is a deliberate call, not an oversight — recorded so the reasoning isn't lost.

## Views die on restart

Buttons stop working after the process restarts. The view object is gone, so presses go unhandled and the user sees "This interaction failed."

Views are also capped at `timeout=180`, which limits the blast radius. Fixing it properly means persistent views: `timeout=None`, explicit `custom_id` on every button, and `bot.add_view()` in `setup_hook`. In [[Backlog]].

## Global sync on every boot

`tree.sync()` runs unconditionally at startup ([[Bot Startup & Lifecycle]]).

- Global commands can take up to an hour to propagate, so testing is slow.
- Syncing on every restart is wasteful, though well inside rate limits at this scale.

Acceptable for one bot in a few servers. A dev-guild sync is in [[Backlog]].

## Hard dependency on a third party

Every game command needs [[Truth or Dare API]]. If it's down, all three degrade to error embeds. Handled gracefully, never a crash — but there's no fallback content. Local packs are in [[Backlog]].

## No rate-limit protection of our own

Nothing stops a user mashing 🎲. We handle 429 when it arrives but don't prevent it, and one spammer can rate-limit the whole bot since the session is shared. A cooldown is in [[Backlog]].

## No tests

Everything is verified by hand. The [[Shared HTTP Session]] error paths were checked with a throwaway fake-session script that wasn't kept. Those are the highest-value unit tests to write — pure logic, no Discord needed: `prompt_text`, `is_error`, `_params_with_rating`, `_fit_field`, and the token-file parser.

## No persistence

No database. Nothing is remembered between restarts — no scores, no per-guild settings, no history. Fine for a stateless prompt bot; blocks several [[Backlog]] items.

## `HelpEntry` is unhashable

`frozen=True` generates `__hash__` but the `List`/`Dict` fields make hashing raise `TypeError`. Harmless today — just never put one in a `set`. See [[Help Registry]].

## Windows console encoding

Never `print()` emoji — a `cp1252` console raises `UnicodeEncodeError`. Log messages stay ASCII. Emoji sent *to Discord* are fine. See [[Bot Startup & Lifecycle]].

## Related
- [[Backlog]] · [[Changelog]]
