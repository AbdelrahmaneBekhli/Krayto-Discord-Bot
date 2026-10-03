"""
One small chat-completions client for every AI command in the bot.

Every provider worth using speaks the OpenAI chat-completions shape, so the
only thing that changes between Groq, OpenRouter, OpenAI and a local Ollama is
a base URL, a model name and a key. Pick one with LLM_PROVIDER.

    LLM_PROVIDER=groq          # groq | openrouter | openai | together | ollama
    LLM_API_KEY=gsk_...        # not needed for ollama
    LLM_MODEL=...              # optional, overrides the provider default
    LLM_BASE_URL=...           # optional, for anything self-hosted

Any of these can live in `.env` or `tokens.txt` next to main.py instead of the
environment, the same way the Discord token does.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path

import aiohttp

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

# provider -> (base url, default model)
PROVIDERS: dict[str, tuple[str, str]] = {
    # Groq retired the Llama models; gpt-oss-120b is the strongest text model
    # it serves now. `GET /models` on your key lists what you can actually use.
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "together": ("https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "ollama": ("http://localhost:11434/v1", "llama3.1"),
}

# Providers you can reach without a key: a box you run yourself.
KEYLESS = {"ollama"}

DEFAULT_TIMEOUT = 25.0


def _from_dotenv(key: str) -> str | None:
    """Look `key` up in .env / tokens.txt, for people who'd rather not set env vars."""
    for name in (".env", "tokens.txt"):
        try:
            raw = (BASE_DIR / name).read_text(encoding="utf-8-sig")
        except OSError:
            continue
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name_part, _, value = line.partition("=")
            if name_part.strip().upper().removeprefix("$ENV:").strip() == key:
                return value.strip().strip("'\"") or None
    return None


def setting(key: str, default: str | None = None) -> str | None:
    return os.getenv(key) or _from_dotenv(key) or default


def provider() -> str:
    return (setting("LLM_PROVIDER") or "groq").strip().lower()


def configured() -> bool:
    """True when there's enough config to attempt a call."""
    name = provider()
    if name not in PROVIDERS and not setting("LLM_BASE_URL"):
        return False
    return bool(setting("LLM_API_KEY")) or name in KEYLESS


def describe() -> str:
    """One line for logs and /help, never including the key."""
    if not configured():
        return "not configured"
    name = provider()
    return f"{name} · {setting('LLM_MODEL') or PROVIDERS.get(name, ('', '?'))[1]}"


def _endpoint_and_model() -> tuple[str, str]:
    name = provider()
    base, model = PROVIDERS.get(name, ("", "gpt-4o-mini"))
    base = (setting("LLM_BASE_URL") or base).rstrip("/")
    return f"{base}/chat/completions", setting("LLM_MODEL") or model


# Optional request fields this provider has rejected. `response_format` and
# `reasoning_effort` are widely but not universally supported -- Groq refuses
# JSON mode for gpt-oss, for instance -- so the first 400 that mentions one
# retires it for the process and every later call goes out without it.
_dropped: set[str] = set()


def _optional_fields(json_object: bool, reasoning_effort: str | None) -> dict:
    fields: dict = {}
    if json_object:
        fields["response_format"] = {"type": "json_object"}
    if reasoning_effort:
        fields["reasoning_effort"] = reasoning_effort
    return {k: v for k, v in fields.items() if k not in _dropped}


async def chat(
    bot,
    *,
    system: str,
    user: str,
    max_tokens: int = 900,
    temperature: float = 1.0,
    json_object: bool = False,
    reasoning_effort: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str | None:
    """
    One completion. Returns the assistant's text, or None on any failure.

    Never raises: every caller here is decorating something that has to work
    without an LLM, so a dead provider must read as "no answer", not an error.
    """
    if not configured():
        return None

    session = getattr(bot, "session", None)
    if session is None or session.closed:
        log.warning("LLM call with no open bot.session")
        return None

    url, model = _endpoint_and_model()
    base: dict = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Content-Type": "application/json"}
    key = setting("LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"

    extras = _optional_fields(json_object, reasoning_effort)

    # Two attempts at most: the retry exists only to shed an optional field the
    # provider turned out not to accept.
    for _ in range(2):
        try:
            async with session.post(
                url,
                json={**base, **extras},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                body = await resp.text() if resp.status >= 400 else None
                if resp.status == 400 and extras:
                    log.info(
                        "LLM %s rejected %s; retrying without it",
                        model, ", ".join(sorted(extras)),
                    )
                    _dropped.update(extras)
                    extras = {}
                    continue
                if resp.status >= 400:
                    log.warning(
                        "LLM %s returned HTTP %s: %s", model, resp.status, body[:300]
                    )
                    return None
                data = await resp.json(content_type=None)
        except asyncio.TimeoutError:
            log.warning("LLM %s timed out after %.0fs", model, timeout)
            return None
        except (aiohttp.ClientError, ValueError):
            log.warning("LLM %s request failed", model, exc_info=True)
            return None

        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            log.warning("LLM %s sent an unexpected body: %s", model, str(data)[:300])
            return None

        if not text:
            # A reasoning model can spend the whole allowance thinking and
            # return nothing at all, which is silent unless we say so.
            log.warning(
                "LLM %s returned no text (finish_reason=%s, %s). Raise "
                "max_tokens or lower LLM_REASONING_EFFORT.",
                model, choice.get("finish_reason"),
                (data.get("usage") or {}).get("completion_tokens_details"),
            )
            return None
        return text

    return None


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


async def chat_json(bot, *, system: str, user: str, **kwargs) -> dict | None:
    """
    `chat` plus JSON parsing. Tolerates a model that wraps it in a code fence.

    JSON mode is only a belt: the model replies with JSON because the prompt
    says to, so `chat` shedding `response_format` costs nothing here.
    """
    text = await chat(bot, system=system, user=user, json_object=True, **kwargs)
    if not text:
        return None
    text = _FENCE.sub("", text.strip())
    # Some models prepend a sentence; fall back to the outermost braces.
    try:
        value = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            log.warning("LLM reply wasn't JSON: %s", text[:200])
            return None
        try:
            value = json.loads(text[start:end + 1])
        except ValueError:
            log.warning("LLM reply wasn't JSON: %s", text[:200])
            return None
    return value if isinstance(value, dict) else None
