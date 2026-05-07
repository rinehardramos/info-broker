"""Provider registry for LLM clients (chat + embeddings).

Supported providers (``LLM_PROVIDER`` env var):
  google    — Gemini via its OpenAI-compatible endpoint for chat and
              native REST API for embeddings (default)
  lmstudio  — Local LM Studio instance (OpenAI-compatible for both)

Notes on Gemini embeddings
--------------------------
The Gemini OpenAI-compatible endpoint (v1beta/openai/) supports chat
completions but NOT embeddings. Embeddings must go through the native
Gemini REST endpoint:
  POST https://generativelanguage.googleapis.com/v1beta/models/<model>:embedContent
"""
from __future__ import annotations

import os

import requests
from openai import OpenAI

_PROVIDERS: dict[str, dict[str, str]] = {
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "chat_model": "gemini-2.5-pro",
        "embedding_model": os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2-preview"),
    },
    "ollama": {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "api_key_env": "OLLAMA_API_KEY",  # not needed but OpenAI client requires it
        "chat_model": os.getenv("OLLAMA_CHAT_MODEL", "llama3"),
        "embedding_model": os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
    },
    "lmstudio": {
        "base_url": os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"),
        "api_key_env": "LM_STUDIO_API_KEY",
        "chat_model": os.getenv("CHAT_MODEL_NAME", "local-model"),
        "embedding_model": os.getenv("EMBEDDING_MODEL_NAME", "local-embed"),
    },
}

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "google")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama")

_GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:embedContent"
)


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


def embed_text(text: str, provider: str | None = None) -> list[float]:
    """Return an embedding vector for ``text`` using the configured provider.

    Provider resolution: explicit arg > EMBEDDING_PROVIDER env > DEFAULT_PROVIDER.
    Supports: ollama (native API), google (Gemini REST), lmstudio (OpenAI-compat).
    """
    if not text:
        return [0.0] * 768

    if provider is None:
        provider = EMBEDDING_PROVIDER

    if provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
        model = embedding_model("ollama")
        resp = requests.post(
            f"{base_url.rstrip('/v1').rstrip('/')}/api/embed",
            json={"model": model, "input": text},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings", [])
        if embeddings:
            return embeddings[0]
        return [0.0] * 768

    if provider == "google":
        api_key = os.getenv("GEMINI_API_KEY", "")
        model = embedding_model("google")
        url = _GEMINI_EMBED_URL.format(model=model)
        resp = requests.post(
            url,
            params={"key": api_key},
            json={
                "model": f"models/{model}",
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": 768,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]

    # lmstudio — OpenAI-compatible embeddings endpoint
    client = build_client(provider)
    response = client.embeddings.create(
        input=[text],
        model=embedding_model(provider),
    )
    return response.data[0].embedding
