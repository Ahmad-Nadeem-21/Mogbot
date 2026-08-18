"""Semantic cache for MogBot.

The cache should reuse similar job descriptions, generated question plans,
rubric decisions, challenge prompts, and coaching report sections when the
stored result is close enough and still valid.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.schemas import MemoryRecord
from core.vector_memory import GlobalVectorMemory


class SemanticCache:
    """Cache interface that can be backed by the global vector database."""

    def __init__(self, memory: GlobalVectorMemory) -> None:
        self.memory = memory

    def lookup(self, cache_type: str, query_text: str, threshold: float = 0.88) -> Optional[Dict[str, Any]]:
        """Return a reusable cached payload when similarity is high enough."""
        matches = self.memory.search(query_text, namespace=f"cache:{cache_type}", top_k=1)
        if not matches:
            return None
        metadata = matches[0].get("metadata", {})
        similarity = float(metadata.get("similarity_score", 0.0))
        if similarity < threshold:
            return None
        return metadata.get("payload")

    def store(self, cache_type: str, key_text: str, payload: Dict[str, Any], metadata: Dict[str, Any]) -> None:
        """Store a cacheable payload with enough metadata to validate reuse."""
        now = datetime.now(timezone.utc).isoformat()
        record: MemoryRecord = {
            "record_id": f"cache-{cache_type}-{uuid.uuid4()}",
            "session_id": str(metadata.get("session_id", "cache")),
            "namespace": f"cache:{cache_type}",
            "text": key_text,
            "metadata": {
                "payload": payload,
                "cache_type": cache_type,
                "created_at": now,
                **metadata,
            },
        }
        self.memory.add_record(record)
