"""Read-only lists: farmers, alerts, runs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import Repository
from ..deps import repo_dep
from ..models import Alert, Farmer, RunRecord, Ticket

router = APIRouter(prefix="/api")


@router.get("/farmers", response_model=list[Farmer])
def farmers(repo: Repository = Depends(repo_dep)) -> list[Farmer]:
    return repo.list_farmers()


@router.get("/alerts", response_model=list[Alert])
def alerts(farmer_id: str | None = None, repo: Repository = Depends(repo_dep)) -> list[Alert]:
    return repo.list_alerts(farmer_id)


@router.get("/runs", response_model=list[RunRecord])
def runs(
    status: str | None = None, kind: str | None = None, limit: int = 20, repo: Repository = Depends(repo_dep)
) -> list[RunRecord]:
    """Newest first. The web app polls this while a question is being answered to find the run that has a
    streaming_url to show in the live viewer."""
    rows = [r for r in repo.list_runs() if (status is None or r.status == status) and (kind is None or r.kind == kind)]
    return rows[: max(1, min(limit, 100))]


@router.get("/runs/{run_id}", response_model=RunRecord)
def run(run_id: str, repo: Repository = Depends(repo_dep)) -> RunRecord:
    found = repo.get_run(run_id)
    if found is None:
        raise HTTPException(404, "run not found")
    return found


@router.get("/tickets", response_model=list[Ticket])
def tickets(status: str | None = None, repo: Repository = Depends(repo_dep)) -> list[Ticket]:
    """List escalation tickets for the hackathon operator dashboard."""
    rows = repo.list_tickets()
    if status is not None:
        if status not in {"open", "closed"}:
            raise HTTPException(422, "status must be open or closed")
        rows = [ticket for ticket in rows if ticket.status == status]
    return rows
