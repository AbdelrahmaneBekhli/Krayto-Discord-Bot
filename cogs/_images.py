"""
One small image-generation client, shaped like `_llm` so it reads the same.

Opt-in: nothing is generated unless IMAGE_PROVIDER is set explicitly, because
this posts generated pictures into other people's servers and calls a third
party to do it. Keylessness is not consent.

    IMAGE_PROVIDER=pollinations   # pollinations | huggingface | custom
    IMAGE_API_KEY=hf_...          # not needed for pollinations
    IMAGE_MODEL=...               # optional, overrides the provider default

Any of these can live in `.env` or `tokens.txt`, like everything else.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

import aiohttp

from cogs._llm import setting

log = logging.getLogger(__name__)

POLLINATIONS, HUGGINGFACE = "pollinations", "huggingface"

DEFAULT_MODELS = {
    POLLINATIONS: "flux",
    HUGGINGFACE: "black-forest-labs/FLUX.1-schnell",
}

KEYLESS = {POLLINATIONS}

# Generous: this is awaited behind a 12-second narration drip, never inline.
DEFAULT_TIMEOUT = 45.0

# Discord's upload ceiling on an unboosted server is 10 MB. Nothing from these
# models comes close, so anything bigger is a redirect or an error page.
MAX_BYTES = 8 * 1024 * 1024

EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def provider() -> str | None:
    name = (setting("IMAGE_PROVIDER") or "").strip().lower()
    return name or None


def configured() -> bool:
    name = provider()
    if name is None or name in {"none", "off"}:
        return False
    if name not in DEFAULT_MODELS and not setting("IMAGE_BASE_URL"):
        return False
    return bool(setting("IMAGE_API_KEY")) or name in KEYLESS


def describe() -> str:
    if not configured():
        return "not configured"
    name = provider()
    return f"{name} · {setting('IMAGE_MODEL') or DEFAULT_MODELS.get(name, '?')}"


async def _pollinations(session, prompt, *, width, height, seed, timeout):
    """Keyless GET: the prompt is the path, the image is the body."""
    url = f"https://image.pollinations.ai/prompt/{quote(prompt, safe='')}"
    params = {
        "width": str(width),
        "height": str(height),
        "nologo": "true",
        "model": setting("IMAGE_MODEL") or DEFAULT_MODELS[POLLINATIONS],
    }
    if seed is not None:
        params["seed"] = str(seed)
    return await session.get(
        url, params=params, timeout=aiohttp.ClientTimeout(total=timeout)
    )


# Hugging Face retired api-inference.huggingface.co -- the hostname no longer
# even resolves -- in favour of the router. This path returns raw image bytes;
# router.huggingface.co/v1/images/generations is the OpenAI-shaped alternative
# and hands back base64 in JSON instead, which is more work for no gain here.
HF_BASE = "https://router.huggingface.co/hf-inference/models"


async def _huggingface(session, prompt, *, width, height, seed, timeout):
    model = setting("IMAGE_MODEL") or DEFAULT_MODELS[HUGGINGFACE]
    base = (setting("IMAGE_BASE_URL") or HF_BASE).rstrip("/")
    payload: dict = {"inputs": prompt, "parameters": {"width": width, "height": height}}
    if seed is not None:
        payload["parameters"]["seed"] = seed
    return await session.post(
        f"{base}/{model}",
        json=payload,
        headers={"Authorization": f"Bearer {setting('IMAGE_API_KEY')}"},
        timeout=aiohttp.ClientTimeout(total=timeout),
    )


async def generate(
    bot,
    prompt: str,
    *,
    width: int = 1024,
    height: int = 576,
    seed: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[bytes, str] | None:
    """
    Render `prompt`. Returns (image bytes, file extension), or None on failure.

    Never raises: every caller is decorating something that must work without
    pictures, so a dead provider has to read as "no image".
    """
    if not configured():
        return None

    session = getattr(bot, "session", None)
    if session is None or session.closed:
        log.warning("Image call with no open bot.session")
        return None

    name = provider()
    call = _pollinations if name == POLLINATIONS else _huggingface

    try:
        async with await call(
            session, prompt, width=width, height=height, seed=seed, timeout=timeout
        ) as resp:
            if resp.status >= 400:
                log.warning("Image %s returned HTTP %s", name, resp.status)
                return None
            kind = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            if kind not in EXTENSIONS:
                log.warning("Image %s sent %s, not an image", name, kind or "nothing")
                return None
            data = await resp.read()
    except asyncio.TimeoutError:
        log.info("Image %s timed out after %.0fs", name, timeout)
        return None
    except (aiohttp.ClientError, ValueError):
        log.warning("Image %s request failed", name, exc_info=True)
        return None

    if not data or len(data) > MAX_BYTES:
        log.warning("Image %s returned %d bytes; discarding", name, len(data))
        return None
    return data, EXTENSIONS[kind]
