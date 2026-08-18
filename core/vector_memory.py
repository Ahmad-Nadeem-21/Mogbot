"""Global vector memory for MogBot.

All agents should use this shared memory layer instead of creating private
vector stores. The first implementation can be local and simple; later it can be
swapped for FAISS, Chroma, Pinecone, or another vector database.
"""

from __future__ import annotations

import json
import math
import re
from hashlib import blake2b
from pathlib import Path
from threading import RLock
from typing import Dict, List

from core.schemas import MemoryRecord

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")
_EMBED_DIM = 64


class GlobalVectorMemory:
    """Thread-safe local vector memory with JSON persistence."""

    def __init__(self, storage_dir: str = "data/vector_db") -> None:
        self._lock = RLock()
        self._records: Dict[str, MemoryRecord] = {}
        self._storage_dir = Path(storage_dir)
        self._storage_file = self._storage_dir / "records.json"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    def _tokenize(self, text: str) -> List[str]:
        return [token.lower() for token in _TOKEN_RE.findall(text)]

    def _embed_text(self, text: str) -> List[float]:
        """Lightweight deterministic embedding for local prototype use."""
        vec = [0.0] * _EMBED_DIM
        for token in self._tokenize(text):
            digest = blake2b(token.encode("utf-8"), digest_size=2).digest()
            idx = int.from_bytes(digest, "big") % _EMBED_DIM
            vec[idx] += 1.0
        norm = math.sqrt(sum(value * value for value in vec))
        if norm == 0.0:
            return vec
        return [value / norm for value in vec]

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        return sum(left * right for left, right in zip(a, b))

    def _load_from_disk(self) -> None:
        if not self._storage_file.exists():
            return
        try:
            with self._storage_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, list):
            return
        for item in data:
            if not isinstance(item, dict):
                continue
            record_id = str(item.get("record_id", ""))
            if not record_id:
                continue
            self._records[record_id] = item

    def _persist_to_disk(self) -> None:
        serializable = list(self._records.values())
        with self._storage_file.open("w", encoding="utf-8") as fh:
            json.dump(serializable, fh, ensure_ascii=True, indent=2)

    def add_record(self, record: MemoryRecord) -> str:
        """Add one embedded record to global memory."""
        record_id = record.get("record_id", "")
        if not record_id:
            raise ValueError("MemoryRecord requires record_id")
        text = record.get("text", "")
        record["embedding"] = record.get("embedding") or self._embed_text(text)
        with self._lock:
            self._records[record_id] = record
            self._persist_to_disk()
        return record_id

    def search(self, query: str, namespace: str = "", top_k: int = 5) -> List[MemoryRecord]:
        """Return similar records for the query."""
        query_embedding = self._embed_text(query)
        with self._lock:
            candidates = [
                record
                for record in self._records.values()
                if not namespace or record.get("namespace", "") == namespace
            ]
            ranked = []
            for record in candidates:
                similarity = self._cosine_similarity(
                    query_embedding,
                    record.get("embedding", []),
                )
                result_record = dict(record)
                result_metadata = dict(result_record.get("metadata", {}))
                result_metadata["similarity_score"] = similarity
                result_record["metadata"] = result_metadata
                ranked.append((similarity, result_record))
            ranked.sort(key=lambda item: item[0], reverse=True)
            return [record for _, record in ranked[: max(top_k, 0)]]

    def upsert_many(self, records: List[MemoryRecord]) -> List[str]:
        """Add or update multiple records safely from one agent thread."""
        stored_ids = []
        with self._lock:
            for record in records:
                record_id = record.get("record_id", "")
                if not record_id:
                    raise ValueError("MemoryRecord requires record_id")
                text = record.get("text", "")
                record["embedding"] = record.get("embedding") or self._embed_text(text)
                self._records[record_id] = record
                stored_ids.append(record_id)
            self._persist_to_disk()
        return stored_ids
