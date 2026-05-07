"""Qdrant collection setup for research_memory."""

from __future__ import annotations

import logging
import os

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

log = logging.getLogger(__name__)

COLLECTION = "research_memory"
VECTOR_DIM = 768


def ensure_research_memory_collection() -> None:
    """Create the research_memory Qdrant collection if it does not already exist."""
    client = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
    )
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        log.info("Created Qdrant collection %r", COLLECTION)
    else:
        log.debug("Qdrant collection %r already exists", COLLECTION)
