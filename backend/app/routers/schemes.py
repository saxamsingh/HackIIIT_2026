from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings
from ..db import Repository
from ..deps import repo_dep, settings_dep, web_dep
from ..discovery import discover
from ..models import SchemeMatch, SchemeReviewRequest, SchemesResponse, Triage
from ..orchestrator import respond
from ..schemes import Scheme, load_schemes, review_scheme
from ..tinyfish import WebClient

router = APIRouter(prefix="/api")


@router.get("/schemes", response_model=SchemesResponse)
async def schemes(
    farmer_id: str | None = None,
    repo: Repository = Depends(repo_dep),
    web: WebClient = Depends(web_dep),
    settings: Settings = Depends(settings_dep),
) -> SchemesResponse:
    farmer = repo.get_farmer(farmer_id) if farmer_id else (repo.list_farmers() or [None])[0]
    if farmer is None:
        raise HTTPException(404, "farmer not found")
    if not load_schemes(settings, reviewed_only=True):
        # Nothing may be shown until a person has reviewed it. That is a state, not an unanswerable question,
        # so it is not escalated (which would open a ticket on every page load).
        return SchemesResponse(
            farmer_id=farmer.id,
            schemes=[],
            confidence=0.0,
            note="No schemes have been reviewed yet. A team member must run `python -m app.cli review <id> "
            "--reviewer <name>` after reading each scheme's sources, or use Operator → Scheme review queue.",
        )
    triage = Triage(
        text="schemes", language=farmer.language, intent="subsidy", crop=farmer.crops[0] if farmer.crops else None
    )
    gated = await respond(triage.text, repo=repo, web=web, settings=settings, farmer_id=farmer.id, forced=triage)
    if gated.status != "answered":
        raise HTTPException(409, gated.reply)
    # Unreviewed schemes are never shown to a farmer, whatever the agent returned.
    matches = [SchemeMatch(**s) for s in gated.data["schemes"] if s.get("reviewed")]
    return SchemesResponse(farmer_id=farmer.id, schemes=matches, confidence=gated.confidence)

@router.post("/schemes/discover")
async def discover_scheme_notices(
    web: WebClient = Depends(web_dep),
    settings: Settings = Depends(settings_dep),
) -> dict[str, object]:
    """Discover candidate notices; candidates remain unpublished until structured rules are reviewed.

    In replay mode this uses fixtures, not live web results. This action may call an external provider in live mode.
    """
    try:
        created = await discover(web, settings)
    except Exception as exc:
        # Never turn an external provider failure into invented candidate records.
        raise HTTPException(502, "Scheme discovery failed; check provider configuration and logs") from exc
    return {
        "mode": web.mode,
        "count": len(created),
        "created": [{"id": scheme.id, "name": scheme.name, "sources": [source.model_dump(mode="json") for source in scheme.sources]} for scheme in created],
        "note": (
            "Replay fixtures were used; no live search was performed."
            if web.mode == "replay"
            else "Candidates are unreviewed and will remain hidden from farmers until their rules are completed and reviewed."
        ),
    }


@router.get("/schemes/review-queue", response_model=list[Scheme])
def scheme_review_queue(settings: Settings = Depends(settings_dep)) -> list[Scheme]:
    """Candidates hidden from farmers until an operator has reviewed the cited sources."""
    return [scheme for scheme in load_schemes(settings) if not scheme.reviewed]


@router.post("/schemes/{scheme_id}/review", response_model=Scheme)
def review_scheme_route(
    scheme_id: str,
    body: SchemeReviewRequest,
    settings: Settings = Depends(settings_dep),
) -> Scheme:
    """Publish one scheme only after a named operator acknowledges reviewing its sources.

    Authentication is not yet implemented; keep this endpoint on localhost/trusted networks.
    """
    if not body.sources_read:
        raise HTTPException(400, "Read the listed sources and confirm before publishing this scheme")
    if not body.reviewer.strip():
        raise HTTPException(422, "Reviewer name is required")
    candidate = next((item for item in load_schemes(settings) if item.id == scheme_id), None)
    if candidate is None:
        raise HTTPException(404, "scheme not found")
    if candidate.discovered and not candidate.eligibility:
        raise HTTPException(422, "Discovered candidate has no structured eligibility rules; add and verify rules before publishing")
    try:
        return review_scheme(settings, scheme_id, body.reviewer.strip())
    except KeyError:
        raise HTTPException(404, "scheme not found") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

