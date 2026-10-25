"""Seed synthetic demo data. Safe to run on every start: rows are keyed by id, so it never duplicates."""

from __future__ import annotations

import json

import yaml

from .config import Settings
from .db import Repository
from .models import Farmer, LedgerEntry, RunRecord


def seed_demo(repo: Repository, settings: Settings) -> list[Farmer]:
    """Load knowledge/demo_farmers.yaml, placing every farmer in DEMO_STATE / DEMO_DISTRICT."""
    path = settings.knowledge_dir / "demo_farmers.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    farmers: list[Farmer] = []
    for item in doc["farmers"]:
        farmer = Farmer(
            id=item["id"],
            name=item["name"],
            phone=item.get("phone"),
            state=settings.demo_state,
            district=settings.demo_district,
            crops=item["crops"],
            land_acres=item["land_acres"],
            category=item["category"],
            language=item["language"],
            documents=item.get("documents", []),
        )
        repo.upsert_farmer(farmer)
        farmers.append(farmer)
        for entry in item.get("ledger_seed", []):
            repo.add_ledger(
                LedgerEntry(
                    id=entry["id"],
                    farmer_id=farmer.id,
                    kind=entry["kind"],
                    amount_rs=entry["amount_rs"],
                    formula=entry["formula"],
                    confirmed=entry["confirmed"],
                )
            )
    _seed_sample_run(repo, settings)
    return farmers


def _seed_sample_run(repo: Repository, settings: Settings) -> None:
    """One replayed Agent run, so the live viewer has a streaming_url to render before any real run."""
    fixture = settings.tinyfish_fixtures_dir / "agent_mandi.json"
    if not fixture.exists():
        return
    response = json.loads(fixture.read_text(encoding="utf-8"))["response"]
    repo.save_run(
        RunRecord(
            id="run_demo_sell",
            kind="agent",
            status=response["status"],
            target=json.loads(fixture.read_text(encoding="utf-8"))["request"]["goal"],
            streaming_url=response["streaming_url"],
            result=response["result"],
            steps=response["num_of_steps"],
            mode="replay",
        )
    )
