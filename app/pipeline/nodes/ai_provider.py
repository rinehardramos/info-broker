from __future__ import annotations

import os
import re

from app.pipeline.nodes.base import RunContext

_DEFAULT_MODELS = {
    "claude": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
    "lm_studio": "local-model",
    "ollama": "llama3",
}

_DEFAULT_BASE_URLS = {
    "lm_studio": "http://localhost:1234/v1",
    "ollama": "http://localhost:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def _render_template(template: str, item: dict) -> str:
    """Substitute {{ item }} and {{ item.field }} placeholders."""
    def replace(m: re.Match) -> str:
        expr = m.group(1).strip()
        if expr == "item":
            return str(item)
        if expr.startswith("item."):
            key = expr[5:]
            return str(item.get(key, ""))
        return m.group(0)

    return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", replace, template)


async def _call_provider(
    provider: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    base_url: str | None,
) -> str:
    if provider == "claude":
        import anthropic
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    if provider == "gemini":
        import google.generativeai as genai  # type: ignore
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        genai.configure(api_key=key)
        gen_model = genai.GenerativeModel(model)
        resp = gen_model.generate_content(prompt)
        return resp.text

    # openai-compatible: openai, openrouter, lm_studio, ollama
    from openai import OpenAI

    effective_url = base_url or _DEFAULT_BASE_URLS.get(provider)

    if provider == "openrouter":
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
    elif provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
    else:
        # Local providers (lm_studio / ollama) don't need a real key
        key = os.getenv("OPENAI_API_KEY", "not-needed")

    client = OpenAI(api_key=key, base_url=effective_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


class AiProviderNode:
    node_type = "ai_provider"
    display_name = "AI Provider"
    category = "enrich"
    config_schema = {
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "title": "Provider",
                "enum": ["claude", "openai", "openrouter", "gemini", "lm_studio", "ollama"],
                "default": "claude",
            },
            "model": {
                "type": "string",
                "title": "Model",
                "default": "claude-haiku-4-5-20251001",
            },
            "prompt_template": {
                "type": "string",
                "title": "Prompt Template",
            },
            "output_field": {
                "type": "string",
                "title": "Output Field",
                "default": "ai_response",
            },
            "base_url": {
                "type": "string",
                "title": "Base URL (LM Studio / Ollama)",
            },
            "temperature": {
                "type": "number",
                "title": "Temperature",
                "default": 0.3,
                "minimum": 0,
                "maximum": 1,
            },
            "max_tokens": {
                "type": "integer",
                "title": "Max Tokens",
                "default": 512,
                "minimum": 1,
                "maximum": 8192,
            },
        },
        "required": ["prompt_template"],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        provider = config.get("provider", "claude")
        model = config.get("model") or _DEFAULT_MODELS.get(provider, "")
        prompt_template = config.get("prompt_template", "")
        output_field = config.get("output_field", "ai_response")
        base_url = config.get("base_url") or None
        temperature = float(config.get("temperature", 0.3))
        max_tokens = int(config.get("max_tokens", 512))

        results = []
        for item in inputs:
            prompt = _render_template(prompt_template, item)
            try:
                response = await _call_provider(
                    provider=provider,
                    model=model,
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    base_url=base_url,
                )
            except RuntimeError:
                raise
            except Exception as exc:
                response = f"error: {exc}"

            results.append({**item, output_field: response})

        return results
