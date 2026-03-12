"""
Minimal vector DB — sparse TF cosine similarity, JSON-backed.
Everything flows through here: skills, tools, workflows, knowledge, agent configs.
"""
import json, math, re, uuid
from pathlib import Path
from typing import Any


class VectorDB:
    def __init__(self, path: Path):
        self.path = path
        self.entries: dict[str, dict] = {}
        self._load()

    # --- core vector ops ---

    def _tokenize(self, text: str) -> dict[str, float]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        freq: dict[str, float] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        n = sum(freq.values()) or 1
        return {w: c / n for w, c in freq.items()}

    def _cosine(self, v1: dict, v2: dict) -> float:
        dot = sum(v1.get(k, 0) * v for k, v in v2.items())
        n1 = math.sqrt(sum(x * x for x in v1.values())) or 1
        n2 = math.sqrt(sum(x * x for x in v2.values())) or 1
        return dot / (n1 * n2)

    # --- CRUD ---

    def add(self, text: str, metadata: dict[str, Any] | None = None) -> str:
        id_ = uuid.uuid4().hex[:8]
        self.entries[id_] = {
            "text": text,
            "vector": self._tokenize(text),
            "metadata": metadata or {},
        }
        self._save()
        return id_

    def update(self, id_: str, text: str, metadata: dict | None = None) -> bool:
        if id_ not in self.entries:
            return False
        self.entries[id_] = {
            "text": text,
            "vector": self._tokenize(text),
            "metadata": metadata or self.entries[id_]["metadata"],
        }
        self._save()
        return True

    def get(self, id_: str) -> dict | None:
        e = self.entries.get(id_)
        return {k: v for k, v in e.items() if k != "vector"} if e else None

    def delete(self, id_: str) -> bool:
        if id_ in self.entries:
            del self.entries[id_]
            self._save()
            return True
        return False

    def search(self, query: str, k: int = 5, type_filter: str | None = None) -> list[dict]:
        q_vec = self._tokenize(query)
        results = []
        for id_, entry in self.entries.items():
            if type_filter and entry["metadata"].get("type") != type_filter:
                continue
            score = self._cosine(q_vec, entry["vector"])
            results.append({
                "id": id_,
                "score": round(score, 4),
                "text": entry["text"],
                "metadata": entry["metadata"],
            })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:k]

    def all(self, type_filter: str | None = None) -> list[dict]:
        return [
            {"id": id_, "text": e["text"], "metadata": e["metadata"]}
            for id_, e in self.entries.items()
            if not type_filter or e["metadata"].get("type") == type_filter
        ]

    # --- persistence ---

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Don't persist the computed vector — rebuild on load
        serializable = {
            id_: {"text": e["text"], "metadata": e["metadata"]}
            for id_, e in self.entries.items()
        }
        self.path.write_text(json.dumps(serializable, indent=2))

    def _load(self):
        if not self.path.exists():
            return
        for id_, entry in json.loads(self.path.read_text()).items():
            entry["vector"] = self._tokenize(entry["text"])
            self.entries[id_] = entry

