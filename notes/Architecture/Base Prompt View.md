---
tags: [architecture, ui]
---

# Base Prompt View

[cogs/questions/_shared/_base_prompt_view.py](cogs/questions/_shared/_base_prompt_view.py)

`BasePromptView(discord.ui.View)` is the shared parent for [[tod]], [[nhie_wyr]] and [[paranoia]]. Subclasses add buttons; the base handles the lock, errors and expiry.

```python
BasePromptView(*, bot, rating: str, owner_id: int | None, timeout: int = 180)
```

| Attribute | Meaning |
|---|---|
| `bot` | For `bot.session` — see [[Shared HTTP Session]] |
| `rating` | Falls back to `"any"` if falsy |
| `owner_id` | `None` = anyone may press |
| `message` | Set by the command so `on_timeout` can edit it |

## The owner lock

Implemented as `interaction_check`, **not** a helper each handler calls:

```python
async def interaction_check(self, interaction) -> bool:
    if self.owner_id is None or interaction.user.id == self.owner_id:
        return True
    await interaction.response.send_message("🔒 This session is locked...", ephemeral=True)
    return False
```

discord.py runs `interaction_check` before **every** child component. Returning `False` stops the callback.

> [!important] Why this replaced the old `guard()`
> It used to be a method each button called as `if not await self.guard(interaction): return`. That works but is opt-in — a new button that forgets the line is silently unlocked. `interaction_check` can't be forgotten.

## Refreshing the embed

```python
await interaction.edit_original_response(embed=embed, view=self)
```

Valid because every handler calls `interaction.response.defer()` first. On a *component* interaction, a bare `defer()` means "deferred message update", so the original message is what gets edited. See [[Interaction Timing]].

## Error surface

`on_error` logs the traceback with the offending item, then tells the user `⚠️ Something went wrong. Please try again.` — picking `followup.send` or `response.send_message` based on `interaction.response.is_done()`, and swallowing `HTTPException` if even that fails. Without this override, a raised exception means the user sees nothing at all.

## Expiry

After `timeout` seconds of no interaction, `on_timeout` disables every button, edits the message to show the dead state, and calls `self.stop()`.

- The edit is wrapped in `except discord.HTTPException` — broad on purpose. The old version caught only `NotFound`, so a deleted channel or revoked permission (`Forbidden`) still raised.
- `isinstance(item, (Button, Select))` guards the `.disabled` assignment, since not every `Item` has that attribute.
- Views are **not persistent**: after a restart, old buttons are dead and go unhandled. See [[Known Gaps]].

## Related
- [[Interaction Timing]]
- [[Shared HTTP Session]]
