---
tags: [meta, design]
---

# Branding

The bot's avatar lives at [assets/avatar.png](assets/avatar.png) — 1024×1024 PNG, a geometric wolf head in bone and brass on deep emerald.

## Why a wolf

It carries the [[mafia]] side of the bot without being literal — werewolf is the game's other name, and a predator among the flock is the whole premise. It also reads at 40px in a member list, which is the only size that really matters.

## Applying it

Discord Developer Portal → the application → **Bot** → click the avatar → upload.

> [!note] Not set from code
> The bot could change its own avatar via the API on startup, but that endpoint is tightly rate-limited and would fire on every restart. Uploading once by hand is correct.

## How it was made

Generated with **Z-Image Turbo** through the Hugging Face connector, then cropped to 88% and resampled to 1024. The crop matters: Discord renders avatars as circles, so a mark composed to the full square loses its edges. 88% fills the circle while keeping the ears clear.

The background is deliberately **solid, not transparent** — a transparent avatar shows Discord's grey through it and looks unfinished.

## Rejected directions

Kept so the same ground isn't covered twice:

| Direction | Why it failed |
|---|---|
| Masquerade mask | A wide rounded shape with two eye holes **is** the Discord logo. Non-starter. |
| Dice and d20 | Ruled out by the owner. A d20 is a die too. |
| **K** monogram | Too plain, and the saturated violet read as childish. |
| Art-deco keyhole, hand-drawn | Thematically apt — secrets and deduction — but hand-drawn linework looked flat rather than crafted. |
| Abstract interlocking diamond | Clean but generic; could belong to any fintech company. |
| Raven | Generated off-centre and read as a seagull. |

> [!tip] The lesson from six rounds of this
> Hand-drawn polygon art is fine for abstract geometry and hopeless for a creature — form, weight and character need real rendering. The moment image generation was available, one prompt beat everything drawn by hand.

## Palette

| Role | Hex |
|---|---|
| Ground | emerald `#17754A`-ish |
| Mark | bone `#F2EAC8` |
| Accent | brass `#D8C98A` |

These aren't the embed colours — those live in `Palette` in `_core.py`, see [[Game Framework]].

## Related
- [[Home]] · [[mafia]]
