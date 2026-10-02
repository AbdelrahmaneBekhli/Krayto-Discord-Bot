from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urljoin

import aiohttp

log = logging.getLogger(__name__)

# Returned under this key when a request could not be fulfilled. Callers use
# `prompt_text()` so an error never gets mistaken for real question content.
ERROR_KEY = "_error"

GENERIC_ERROR = "⚠️ Couldn't reach the question API. Try again in a moment."
RATE_LIMIT_ERROR = "⏳ Rate-limited. Try again in a few seconds."


def _params_with_rating(rating: str | None) -> dict[str, str]:
    if not rating or rating == "any":
        return {}
    return {"rating": rating}


async def api_get(bot, base: str, path: str, rating: str | None = None) -> dict[str, Any]:
    """
    GET a prompt from the API.

    Always returns a dict: either the decoded payload, or `{ERROR_KEY: "..."}`
    with a user-facing message. Never raises for network/API failures.
    """
    session = getattr(bot, "session", None)
    if session is None or session.closed:
        raise RuntimeError("Bot has no open session. Did you create bot.session in setup_hook?")

    url = urljoin(base + "/", path.lstrip("/"))

    try:
        async with session.get(url, params=_params_with_rating(rating)) as resp:
            if resp.status == 429:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    return {ERROR_KEY: f"⏳ Rate-limited. Try again in {retry_after}s."}
                return {ERROR_KEY: RATE_LIMIT_ERROR}

            if resp.status >= 400:
                log.warning("API %s returned HTTP %s", url, resp.status)
                return {ERROR_KEY: f"⚠️ API error (HTTP {resp.status}). Try again shortly."}

            # The API sends JSON; content_type=None keeps a stray header from
            # turning a valid body into an exception.
            data = await resp.json(content_type=None)
    except asyncio.TimeoutError:
        log.warning("API %s timed out", url)
        return {ERROR_KEY: "⏳ The question API timed out. Try again."}
    except aiohttp.ClientError:
        log.warning("API %s request failed", url, exc_info=True)
        return {ERROR_KEY: GENERIC_ERROR}
    except ValueError:  # includes json.JSONDecodeError
        log.warning("API %s returned non-JSON body", url)
        return {ERROR_KEY: "⚠️ API returned an unexpected response."}

    if not isinstance(data, dict):
        log.warning("API %s returned %s, expected an object", url, type(data).__name__)
        return {ERROR_KEY: "⚠️ API returned an unexpected response."}

    return data


def prompt_text(data: dict[str, Any]) -> str:
    """Pull the display text out of an `api_get` result."""
    if error := data.get(ERROR_KEY):
        return str(error)

    question = data.get("question")
    if isinstance(question, str) and question.strip():
        return question.strip()
    return "No prompt found."


def is_error(data: dict[str, Any]) -> bool:
    return ERROR_KEY in data
