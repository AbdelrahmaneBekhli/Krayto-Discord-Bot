---
tags: [command, game]
category: Games
file: cogs/games/mafia.py
---

# /mafia

Social deduction. [cogs/games/mafia.py](cogs/games/mafia.py)

No options — everything is configured in the lobby. One game per channel, enforced by the registry in [[Game Framework]].

## Roles

| Role | Night action |
|---|---|
| 🔪 **Mafia** | Pick someone to eliminate. Team shares one target; last pick wins. |
| 🔍 **Detective** | Investigate a player, learn whether they're Mafia. |
| 💉 **Doctor** | Protect a player from being killed. May self-protect. |
| 🚔 **Police** | **Detain** a player: they can't act, and can't be killed. |
| 🧑‍🌾 **Villager** | None. Talk and vote. |

> [!note] Police is not a second Detective
> Detective and Police are usually the same role. Police was given **detain** instead so it's mechanically distinct: it's both a roleblock *and* a save, which makes it strong — hence the default of 0. Changing it means editing one `Role` entry and the matching branch in `TargetSelect.callback`.

## Host setup

The **Roles** button (host only, ephemeral) gives four dropdowns for Mafia / Detective / Doctor / Police counts, 0–5 each (Mafia 1–5). Everyone left over becomes a Villager. The lobby line updates live as counts change.

`Settings.validate()` blocks three bad setups, with the fix in the message:

- fewer than 1 Mafia
- more special roles than players
- `mafia * 2 >= players` — unwinnable for the town

## Flow

```
Lobby → roles dealt → 🎭 reveal → 🌙 night → ☀️ day → 🗳️ vote → (repeat) → end
```

**Night** auto-resolves the moment every living actor has submitted; the host can `⏭️ Force dawn` if someone's idle. **Vote** closes when every living player has voted, or on `⏱️ Close the vote`. Plurality eliminates; **any tie eliminates nobody**.

## Night resolution order

Order matters, and `resolve_night()` applies it deliberately:

1. **Police detain** — always lands (Police can't be blocked).
2. **Doctor protect** — only if that doctor wasn't detained. Each doctor is tracked individually, so detaining one doesn't cancel another's save.
3. **Mafia kill** — skipped if every living Mafia is detained, or the target is protected. Detained players are protected too.
4. **Detective** — result is withheld if that detective was detained.

> [!bug] The first version got this wrong
> Protect and detain were stored as flat sets of *targets*, losing who acted. With two Doctors, detaining one cancelled both saves. They're now `dict[actor_id, target_id]`. The regression test is "second doctor still saves".

## Win conditions

- **Town** — no Mafia left alive.
- **Mafia** — Mafia count ≥ town count (parity, not a majority).

## Why no DMs

Every private moment is a **button → ephemeral reply**, never a DM. DMs fail silently when a user has them closed, which would stall a game mid-round with no clear cause. Ephemerals always work and need no setup.

The one exception is the Detective's result, which is DM'd so it survives the phase change — wrapped in `try/except HTTPException`, and they can re-read their card from **My role** if it fails.

## Known limits

- Select menus cap at 25 options, so `max_players` is 25.
- Dead players aren't muted — the bot can't enforce silence. Social convention only.
- No persistence: a restart loses the game. See [[Known Gaps]].
- Simulated games with *random* voting go ~83% Mafia. That's the simulation having no deduction, not a balance bug — real players vote on information.

## Related
- [[Game Framework]] · [[wavelength]]
