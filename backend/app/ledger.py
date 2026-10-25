"""Rs Unlocked: projected until the farmer confirms. CLAUDE.md section 2.10."""

from __future__ import annotations

from typing import Literal

from .db import Repository
from .models import LedgerEntry, LedgerResponse, now


def project(
    repo: Repository,
    farmer_id: str,
    kind: Literal["sell", "subsidy", "claim"],
    amount_rs: float,
    formula: str,
) -> LedgerEntry | None:
    """Record a projected entry. Asking the same question twice must not inflate the total, so an unconfirmed
    entry with the same farmer, kind and formula is refreshed instead of duplicated. Zero or negative
    amounts are not recorded."""
    if amount_rs <= 0:
        return None
    for existing in repo.list_ledger(farmer_id):
        if existing.kind == kind and existing.formula == formula and not existing.confirmed:
            return repo.add_ledger(existing.model_copy(update={"amount_rs": amount_rs, "created_at": now()}))
    return repo.add_ledger(LedgerEntry(farmer_id=farmer_id, kind=kind, amount_rs=amount_rs, formula=formula))


def summary(repo: Repository, farmer_id: str | None = None) -> LedgerResponse:
    entries = repo.list_ledger(farmer_id)
    return LedgerResponse(
        farmer_id=farmer_id,
        total_rs=sum(e.amount_rs for e in entries if e.confirmed),
        projected_rs=sum(e.amount_rs for e in entries if not e.confirmed),
        entries=entries,
    )
