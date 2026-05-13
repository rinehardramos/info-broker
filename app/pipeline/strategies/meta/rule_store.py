"""RAG-based strategy rule store — index and retrieve relevant rules from Qdrant."""
from __future__ import annotations
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

COLLECTION = "strategy_rules"
EMBEDDING_DIM = 768  # Match existing embedding dimension


def _get_qdrant():
    """Get Qdrant client."""
    from qdrant_client import QdrantClient
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )


def _embed(text: str) -> list[float]:
    """Embed text using the same embedding function as the rest of the system."""
    try:
        from llm_providers import embed_text
        return embed_text(text)
    except Exception:
        # Fallback: return zero vector (won't match well but won't crash)
        return [0.0] * EMBEDDING_DIM


def _rule_id(name: str) -> str:
    """Deterministic UUID from rule name."""
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"rule:{name}"))


def index_rules(rules: list[dict]) -> int:
    """Index a list of rules to Qdrant.

    Each rule dict has: name, category, entity_types, always_on, priority, rule_text, tokens.
    Returns count indexed.
    """
    try:
        from qdrant_client.models import PointStruct, VectorParams, Distance
        client = _get_qdrant()

        # Ensure collection exists
        try:
            client.get_collection(COLLECTION)
        except Exception:
            client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )

        points = []
        for rule in rules:
            vector = _embed(f"{rule['name']} {rule['rule_text'][:200]}")
            points.append(PointStruct(
                id=_rule_id(rule["name"]),
                vector=vector,
                payload={
                    "name": rule["name"],
                    "category": rule.get("category", "universal"),
                    "entity_types": rule.get("entity_types", ["all"]),
                    "always_on": rule.get("always_on", False),
                    "priority": rule.get("priority", 2),
                    "rule_text": rule["rule_text"],
                    "tokens": rule.get("tokens", len(rule["rule_text"]) // 4),
                },
            ))

        if points:
            client.upsert(collection_name=COLLECTION, points=points)

        return len(points)
    except Exception as exc:
        log.warning("Rule indexing failed: %s", exc)
        return 0


def retrieve_rules(query: str, entity_type: str = "person", max_tokens: int = 1500) -> str:
    """Retrieve relevant rules for a query context. Returns formatted text."""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue
        client = _get_qdrant()

        # Check if collection exists
        try:
            client.get_collection(COLLECTION)
        except Exception:
            log.debug("strategy_rules collection not found, falling back to static")
            return ""

        # 1. Get always-on rules (priority 1)
        always_on = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(must=[
                FieldCondition(key="always_on", match=MatchValue(value=True)),
            ]),
            limit=20,
        )[0]

        # 2. Semantic search for relevant rules
        vector = _embed(query)
        entity_filter = Filter(should=[
            FieldCondition(key="entity_types", match=MatchAny(any=["all", entity_type])),
        ])

        hits = client.query_points(
            collection_name=COLLECTION,
            query=vector,
            query_filter=entity_filter,
            limit=20,
            with_payload=True,
        ).points

        # 3. Combine, deduplicate, respect token budget
        selected: dict[str, dict] = {}
        token_count = 0

        # Always-on first
        for point in always_on:
            name = point.payload["name"]
            tokens = point.payload.get("tokens", 50)
            if token_count + tokens <= max_tokens:
                selected[name] = point.payload
                token_count += tokens

        # Then semantic matches
        for hit in hits:
            name = hit.payload["name"]
            if name in selected:
                continue
            tokens = hit.payload.get("tokens", 50)
            if token_count + tokens > max_tokens:
                break
            selected[name] = hit.payload
            token_count += tokens

        if not selected:
            return ""

        # 4. Format as compact text
        lines = ["## INVESTIGATION RULES (context-relevant)\n"]
        for rule in sorted(selected.values(), key=lambda r: r.get("priority", 2)):
            lines.append(rule["rule_text"].strip())
            lines.append("")

        return "\n".join(lines)

    except Exception as exc:
        log.warning("Rule retrieval failed, falling back to static: %s", exc)
        return ""


def index_from_meta_files() -> int:
    """Parse all meta-strategy files and index their rules to Qdrant."""
    import importlib
    import importlib.util
    import pathlib

    meta_dir = pathlib.Path(__file__).parent
    rules = []

    for py_file in sorted(meta_dir.glob("*.py")):
        if py_file.name in ("__init__.py", "compiler.py", "rule_store.py"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"meta.{py_file.stem}", py_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, "STRATEGY_TEXT"):
                continue

            text = mod.STRATEGY_TEXT.strip()
            name = getattr(mod, "NAME", py_file.stem)
            entity_types = getattr(mod, "ENTITY_TYPES", ["all"])
            always_on = getattr(mod, "ALWAYS_ON", False)

            # Split into individual rules by section headers
            sections = _split_into_rules(text, name)
            for section in sections:
                rules.append({
                    "name": section["name"],
                    "category": name,
                    "entity_types": entity_types,
                    "always_on": always_on,
                    "priority": 1 if always_on else 2,
                    "rule_text": section["text"],
                    "tokens": len(section["text"]) // 4,
                })
        except Exception as exc:
            log.debug("Failed to parse %s: %s", py_file, exc)

    return index_rules(rules)


def _split_into_rules(text: str, parent_name: str) -> list[dict]:
    """Split a strategy text into individual rule chunks."""
    import re
    # Split on lines that look like rule headers (ALL CAPS or === PREFIX ===)
    chunks = re.split(r'\n(?=[A-Z][A-Z_\s]{3,}:|\=\=\=)', text)

    valid_chunks = [c.strip() for c in chunks if c.strip() and len(c.strip()) >= 20]

    # No header-based split — return the whole text under the parent name
    if len(valid_chunks) <= 1:
        return [{"name": parent_name, "text": text}]

    rules = []
    for chunk in valid_chunks:
        first_line = chunk.split('\n')[0].strip().rstrip(':').strip('= ').strip()
        rule_name = f"{parent_name}__{first_line[:50].lower().replace(' ', '_')}"
        rules.append({"name": rule_name, "text": chunk})

    return rules
