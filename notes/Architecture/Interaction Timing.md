---
tags: [architecture, gotcha]
---

# Interaction Timing

> [!danger] The 3-second rule
> Discord kills an interaction that gets no response within **3 seconds**. Replying after that fails with `404 Unknown interaction` and the user sees "The application did not respond."

The shared `aiohttp` timeout is **10 seconds** ([[Shared HTTP Session]]) — more than three times the budget. So any handler that calls the API before responding is a live bug waiting on a slow upstream.

## The rule in this codebase

**Defer first, then fetch, then send.**

### Slash commands

```python
await interaction.response.defer()          # buys ~15 minutes
data = await fetch_tod(self.bot, kind, rating)
view.message = await interaction.followup.send(embed=..., view=view, wait=True)
```

`wait=True` makes `followup.send` return the `Message`, which is stored on the view so [[Base Prompt View]]'s `on_timeout` can edit it later. Without `wait=True` it returns `None`.

### Button callbacks

```python
await interaction.response.defer()          # deferred message *update*
data = await fetch_tod(...)
await self.update_message(interaction, embed=...)   # edit_original_response
```

## History

All three commands originally fetched **before** `send_message`:

```python
data = await fetch_tod(self.bot, first_kind, selected_rating)   # could take 10s
await interaction.response.send_message(embed=..., view=view)   # too late
```

This was the most serious bug in the project — intermittent and load-dependent, so it would look like "the bot is flaky" rather than a clear failure.

## Checklist for new commands

- [ ] Does it `await` anything before responding? → `defer()` first
- [ ] Does it need the message object later? → `followup.send(..., wait=True)`
- [ ] Button handler? → `defer()` then `edit_original_response`
- [ ] Ephemeral? → decide at `defer(ephemeral=True)`, not at send time

## Related
- [[Base Prompt View]]
- [[Known Gaps]]
