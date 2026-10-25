"""TINYFISH_RECORD=1: save a live response as a replay fixture, so the demo can run with Wi-Fi off."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def record_fixture(directory: Path, kind: str, request: dict[str, Any], response: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    key = json.dumps([kind, request], sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
    hint = re.sub(r"[^a-z0-9]+", "-", str(next(iter(request.values()), "")).lower()).strip("-")[:32]
    path = directory / f"{kind}_rec_{hint}_{digest}.json"
    doc = {"_label": "RECORDED from a live TinyFish response.", "kind": kind, "request": request, "response": response}
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
