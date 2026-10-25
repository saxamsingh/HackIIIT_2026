from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import ledger as ledger_service
from ..db import Repository
from ..deps import repo_dep
from ..models import LedgerEntry, LedgerResponse

router = APIRouter(prefix="/api")


@router.get("/ledger", response_model=LedgerResponse)
def ledger(farmer_id: str | None = None, repo: Repository = Depends(repo_dep)) -> LedgerResponse:
    return ledger_service.summary(repo, farmer_id)


@router.post("/ledger/{entry_id}/confirm", response_model=LedgerEntry)
def confirm(entry_id: str, repo: Repository = Depends(repo_dep)) -> LedgerEntry:
    """The farmer's yes. Only a confirmed entry counts towards Rs Unlocked; nothing is submitted anywhere."""
    try:
        return repo.confirm_ledger(entry_id)
    except KeyError:
        raise HTTPException(404, "ledger entry not found") from None
