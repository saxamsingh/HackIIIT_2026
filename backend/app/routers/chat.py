from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..channels.notify import Notifier
from ..config import Settings
from ..db import Repository
from ..deps import notifier_dep, repo_dep, settings_dep, web_dep
from ..models import ChatRequest, GatedResponse, SellRequest, Triage
from ..orchestrator import respond
from ..tinyfish import WebClient

router = APIRouter(prefix="/api")


@router.post("/chat", response_model=GatedResponse)
async def chat(
    body: ChatRequest,
    repo: Repository = Depends(repo_dep),
    web: WebClient = Depends(web_dep),
    settings: Settings = Depends(settings_dep),
    notifier: Notifier = Depends(notifier_dep),
) -> GatedResponse:
    if body.farmer_id and repo.get_farmer(body.farmer_id) is None:
        raise HTTPException(404, "farmer not found")
    return await respond(
        body.text, repo=repo, web=web, settings=settings, farmer_id=body.farmer_id, notifier=notifier
    )


@router.post("/sell", response_model=GatedResponse)
async def sell(
    body: SellRequest,
    repo: Repository = Depends(repo_dep),
    web: WebClient = Depends(web_dep),
    settings: Settings = Depends(settings_dep),
    notifier: Notifier = Depends(notifier_dep),
) -> GatedResponse:
    farmer = repo.get_farmer(body.farmer_id) if body.farmer_id else None
    if body.farmer_id and farmer is None:
        raise HTTPException(404, "farmer not found")
    triage = Triage(
        text=f"sell {body.crop} {body.quantity_qtl:g} quintal",
        language=farmer.language if farmer else "en",
        intent="sell",
        crop=body.crop,
        quantity_qtl=body.quantity_qtl,
    )
    return await respond(
        triage.text,
        repo=repo,
        web=web,
        settings=settings,
        farmer_id=body.farmer_id,
        forced=triage,
        notifier=notifier,
    )
