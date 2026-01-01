from __future__ import annotations
from urllib.parse import urljoin

def _params_with_rating(rating: str) -> dict:
    return {} if rating == "any" else {"rating": rating}

async def api_get(bot, base: str, path: str, rating: str | None = None) -> dict:
    if not getattr(bot, "session", None):
        raise RuntimeError("Bot has no session. Did you create bot.session in setup_hook?")

    url = urljoin(base + "/", path.lstrip("/"))
    params = _params_with_rating(rating) if rating else {}

    async with bot.session.get(url, params=params) as resp:
        if resp.status == 429:
            return {"question": "⏳ Rate-limited. Try again in a few seconds."}
        try:
            return await resp.json()
        except Exception:
            return {"question": "⚠️ API returned an unexpected response."}