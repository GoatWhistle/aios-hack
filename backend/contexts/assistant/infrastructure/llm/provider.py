from __future__ import annotations

from backend.contexts.assistant.domain.errors import (
    NoApiKeyError,
)

import os
from typing import Mapping
from urllib.parse import urlsplit

from backend.contexts.assistant.infrastructure.llm.anthropic_chat import AnthropicChatClient
from backend.contexts.assistant.infrastructure.llm.chat import ChatClient
from backend.contexts.assistant.infrastructure.llm.compatible import OpenAICompatibleClient
from backend.contexts.assistant.infrastructure.llm.openrouter import (
    DEFAULT_MODEL,
    OpenRouterClient,
)

PROVIDER_ENV_VAR = "JARVIS_PROVIDER"
MODEL_ENV_VAR = "JARVIS_MODEL"
MAX_TOKENS_ENV_VAR = "JARVIS_MAX_TOKENS"
OPENROUTER_KEY_VAR = "OPENROUTER_API_KEY"
ANTHROPIC_KEY_VAR = "ANTHROPIC_API_KEY"
ANTHROPIC_FALLBACK_MODEL = "claude-sonnet-4-5"
DEFAULT_MAX_TOKENS = 2400


def _max_tokens(env: Mapping[str, str]) -> int:
    raw = env.get(MAX_TOKENS_ENV_VAR)
    if not raw:
        return DEFAULT_MAX_TOKENS
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(
            f"{MAX_TOKENS_ENV_VAR}={raw!r} is not a number: the answer length "
            "limit must be an integer"
        ) from error
    if value <= 0:
        raise RuntimeError(f"{MAX_TOKENS_ENV_VAR} must be positive")
    return value


def build_client(env: Mapping[str, str] | None = None) -> ChatClient:
    values = env if env is not None else os.environ
    preferred = (values.get(PROVIDER_ENV_VAR) or "openrouter").strip().lower()
    if preferred not in ("openrouter", "anthropic", "openai-compatible"):
        raise RuntimeError(
            f"{PROVIDER_ENV_VAR}={preferred!r} is not supported: the allowed "
            "values are openrouter, anthropic and openai-compatible"
        )
    openrouter_key = values.get(OPENROUTER_KEY_VAR) or ""
    anthropic_key = values.get(ANTHROPIC_KEY_VAR) or ""
    max_tokens = _max_tokens(values)
    if preferred == "openai-compatible":
        key = values.get("JARVIS_API_KEY") or ""
        if not key:
            raise NoApiKeyError("JARVIS_API_KEY is required for openai-compatible")
        base_url = (values.get("JARVIS_BASE_URL") or "").strip().rstrip("/")
        parsed = urlsplit(base_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {
            "localhost", "127.0.0.1", "::1",
        }
        if (
            not parsed.hostname
            or (parsed.scheme != "https" and not local_http)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
        ):
            raise RuntimeError(
                "JARVIS_BASE_URL must be an HTTPS API base URL "
                "(HTTP allowed only on localhost), "
                "without credentials, query or fragment"
            )
        model = (values.get(MODEL_ENV_VAR) or "").strip()
        if not model:
            raise RuntimeError("JARVIS_MODEL is required for openai-compatible")
        return OpenAICompatibleClient(
            api_key=key, base_url=base_url, model=model, max_tokens=max_tokens,
        )
    order = (
        ("openrouter", "anthropic")
        if preferred == "openrouter"
        else ("anthropic", "openrouter")
    )
    for name in order:
        if name == "openrouter" and openrouter_key:
            return OpenRouterClient(
                api_key=openrouter_key,
                model=values.get(MODEL_ENV_VAR) or DEFAULT_MODEL,
                max_tokens=max_tokens,
            )
        if name == "anthropic" and anthropic_key:
            model = values.get(MODEL_ENV_VAR) or ANTHROPIC_FALLBACK_MODEL
            if "/" in model:
                model = model.split("/", 1)[1]
            return AnthropicChatClient(
                api_key=anthropic_key, model=model, max_tokens=max_tokens
            )
    raise NoApiKeyError(
        f"neither {OPENROUTER_KEY_VAR} nor {ANTHROPIC_KEY_VAR} is set: Jarvis "
        "cannot reach a model. The service still starts and answers 503; "
        "the frontend shows a connection error"
    )
