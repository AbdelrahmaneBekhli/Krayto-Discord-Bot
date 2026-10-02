---
tags: [command, game]
category: Games
file: cogs/games/wavelength.py
---

# /wavelength

Read your friends' minds. [cogs/games/wavelength.py](cogs/games/wavelength.py)

No options. One game per channel, enforced by the registry in [[Game Framework]].

## How a round works

1. A **Psychic** is chosen (rotating, shuffled once at the start).
2. They privately see a spectrum — e.g. **Underrated ↔ Overrated** — and a secret spot, **1–10**.
3. They give one clue that sits exactly on that spot. No numbers, no pointing.
4. Everyone else privately picks a band 1–10 from a dropdown, shown as a `───●──────` gauge.
5. Reveal scores everyone.

The game ends after **every player has been Psychic once**, then prints final scores.

## Scoring

| Distance from the spot | Points |
|---|---|
| Exact band | **4** 🎯 |
| 1 off | **2** |
| 2 off | **1** |
| 3+ | 0 |

The Psychic scores the **average of their guessers**, rounded. That's the design decision worth keeping: it means a clue that lands everyone near the spot pays better than a clever one only your best friend gets, so the Psychic is playing *with* the room rather than at it.

## 10 bands, not a slider

Discord has no slider. Twenty bands would be more precise but makes a 20-item dropdown, and the scoring bands would be too fine to feel fair. Ten reads at a glance and keeps the dropdown short.

## Spectrum pool

45 pairs in `SPECTRUMS`. Each game draws without replacement from a per-game copy, so one session never repeats a spectrum; the pool refills if a game somehow outruns it. Adding more is just appending tuples.

## The modal detour

A modal can only be opened from a *fresh* interaction, and the Psychic button already spends its interaction showing the secret spot. So that flow sends the spot ephemerally, then a second ephemeral with a **Write my clue** button (`_ClueLauncher`) whose interaction opens the modal.

> [!note] Not a workaround for a bug
> This is just how Discord interactions work — one response per interaction, and `send_modal` must be the response. The extra click also doubles as "I've read my spot, I'm ready".

## Reveal

Host *or* Psychic can reveal, once at least one guess is in. The public counter updates live as people lock in, so you can see who's still thinking without nagging.

## Known limits

- No persistence — a restart loses the game. See [[Known Gaps]].
- Nothing stops the Psychic typing a number as their clue. Social convention, same as the real game.

## Related
- [[Game Framework]] · [[mafia]]
