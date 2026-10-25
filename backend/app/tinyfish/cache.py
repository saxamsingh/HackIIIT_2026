"""On-disk response cache for live Search and Fetch (never for Agent runs, which have side effects)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class DiskCache:
    def __init__(self, directory: Path, ttl_seconds: int) -> None:
        self.directory = directory
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def key(kind: str, request: dict[str, Any]) -> str:
        canonical = json.dumps([kind, request], sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _path(self, kind: str, request: dict[str, Any]) -> Path:
        return self.directory / f"{kind}_{self.key(kind, request)[:24]}.json"

    def get(self, kind: str, request: dict[str, Any]) -> Any | None:
        path = self._path(kind, request)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if time.time() - entry["stored_at"] > self.ttl_seconds:
            return None
        return entry["value"]

    def put(self, kind: str, request: dict[str, Any], value: Any) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        entry = {"stored_at": time.time(), "value": value}
        self._path(kind, request).write_text(
            json.dumps(entry, ensure_ascii=False, default=str), encoding="utf-8"
        )
