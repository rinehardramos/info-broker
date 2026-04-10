"""Provider registry for LLM clients (chat + embeddings).

Supported providers (``LLM_PROVIDER`` env var):
  google    — Gemini via its OpenAI-compatible endpoint (default)
  lmstudio  — Local LM Studio instance
"""
from __future__ import annotations

import os

from openai import OpenAI

_PROVIDERS: dict[str, dict[str, str]] = {
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "chat_model": "gemini-2.5-pro",
        "embedding_model": "text-embedding-004",
    },
    "lmstudio": {
        "base_url": os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"),
        "api_key_env": "LM_STUDIO_API_KEY",
        "chat_model": os.getenv("CHAT_MODEL_NAME", "local-model"),
        "embedding_model": os.getenv("EMBEDDING_MODEL_NAME", "local-embed"),
    },
}

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "google")


def build_client(provider: str = DEFAULT_PROVIDER) -> OpenAI:
    cfg = _PROVIDERS.get(provider)
    if cfg is None:
        raise ValueError(f"Unknown LLM provider {provider!r}. Choose from: {list(_PROVIDERS)}")
    api_key = os.getenv(cfg["api_key_env"], "")
    return OpenAI(base_url=cfg["base_url"], api_key=api_key)


def chat_model(provider: str = DEFAULT_PROVIDER) -> str:
    return _PROVIDERS.get(provider, _PROVIDERS["google"])["chat_model"]


def embedding_model(provider: str = DEFAULT_PROVIDER) -> str:
    return _PROVIDERS.get(provider, _PROVIDERS["google"])["embedding_model"]
