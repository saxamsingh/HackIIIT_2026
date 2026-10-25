"""Regenerate web/src/mocks/*.json from the real API running in replay mode.

The web app falls back to these files only when the backend cannot be reached, so they must keep the exact
shape of the live responses. Run after changing a response model, from the repo root:

    backend/.venv/Scripts/python scripts/export_mocks.py        (Windows)
    backend/.venv/bin/python scripts/export_mocks.py            (macOS / Linux)

The schemes in the sample are reviewed by "mock-export" on a throwaway copy of knowledge/; that is a
labelled offline sample and says nothing about the real review status of the files in the repository."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.factory import create_app  # noqa: E402
from app.schemes import load_schemes, review_scheme  # noqa: E402

OUT = ROOT / "web" / "src" / "mocks"


def dump(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", f"web/src/mocks/{name}.json")


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="khetkaaj-mocks-"))
    knowledge = work / "knowledge"
    shutil.copytree(ROOT / "knowledge", knowledge)
    settings = Settings(
        _env_file=None, tinyfish_mode="replay", db_backend="sqlite", sqlite_path=work / "mock.db",
        files_dir=work / "files", cache_dir=work / "cache", knowledge_dir=knowledge,
        demo_state="Uttar Pradesh", demo_district="Meerut",
    )
    for s in load_schemes(settings):
        review_scheme(settings, s.id, "mock-export (automated sample, not a human review)")
    c = TestClient(create_app(settings))
    farmer = "farmer_demo_1"

    dump("farmers", c.get("/api/farmers").json())
    dump("sell", c.post("/api/sell", json={"crop": "wheat", "quantity_qtl": 20, "farmer_id": farmer}).json())
    dump("chat_dose", c.post("/api/chat", json={"text": "Chlorpyrifos kitna ml dalu?", "farmer_id": farmer}).json())
    dump("chat_menu", c.post("/api/chat", json={"text": "hello", "farmer_id": farmer}).json())
    dump("schemes", c.get("/api/schemes", params={"farmer_id": farmer}).json())
    claim = {"farmer_id": farmer, "crop": "wheat", "event": "hail", "event_date": date.today().isoformat()}
    dump("claim", c.post("/api/claim", json=claim).json())
    c.post("/demo/replay-monitor", json={"fixture_name": "hail"})
    dump("alerts", c.get("/api/alerts").json())
    dump("ledger", c.get("/api/ledger", params={"farmer_id": farmer}).json())
    dump("runs", c.get("/api/runs").json())
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
