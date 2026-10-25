from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..channels.notify import Notifier
from ..config import Settings
from ..db import Repository
from ..deps import notifier_dep, repo_dep, settings_dep, web_dep
from ..exif import PhotoMeta, read_photo
from ..models import ClaimRequest, ClaimResponse, GatedResponse, Triage
from ..orchestrator import respond
from ..tinyfish import WebClient

router = APIRouter(prefix="/api")

MAX_PHOTOS = 8
MAX_PHOTO_BYTES = 10 * 1024 * 1024
EVENTS = {"hail", "heavy_rain", "flood", "other"}


async def _run_claim(
    *,
    farmer_id: str,
    crop: str,
    event: str,
    event_date: str,
    photos: list[PhotoMeta],
    repo: Repository,
    web: WebClient,
    settings: Settings,
    notifier: Notifier,
) -> ClaimResponse:
    farmer = repo.get_farmer(farmer_id)
    if farmer is None:
        raise HTTPException(404, "farmer not found")
    try:
        date.fromisoformat(event_date)
    except ValueError:
        raise HTTPException(422, "event_date must be an ISO date (YYYY-MM-DD)") from None
    triage = Triage(text=f"claim {event} {crop}", language=farmer.language, intent="claim", crop=crop)
    extra: dict[str, Any] = {
        "claim": {"crop": crop, "event": event, "event_date": event_date, "photos": photos}
    }
    gated: GatedResponse = await respond(
        triage.text, repo=repo, web=web, settings=settings, farmer_id=farmer.id, forced=triage,
        extra=extra, notifier=notifier,
    )
    if gated.status != "answered":
        raise HTTPException(409, gated.reply)
    d = gated.data
    return ClaimResponse(
        claim_id=d["claim_id"],
        dossier_url=d["dossier_url"],
        intimation_deadline=d.get("intimation_deadline"),
        warnings=d.get("warnings", []),
        evidence=gated.evidence,
        confidence=gated.confidence,
    )


@router.post("/claim", response_model=ClaimResponse)
async def claim(
    body: ClaimRequest,
    repo: Repository = Depends(repo_dep),
    web: WebClient = Depends(web_dep),
    settings: Settings = Depends(settings_dep),
    notifier: Notifier = Depends(notifier_dep),
) -> ClaimResponse:
    """Photo file names only: their capture time and GPS cannot be checked without the files, so the dossier
    says so. Use POST /api/claim/photos to upload the photos."""
    return await _run_claim(
        farmer_id=body.farmer_id,
        crop=body.crop,
        event=body.event,
        event_date=body.event_date,
        photos=[PhotoMeta(n) for n in body.photo_names],
        repo=repo,
        web=web,
        settings=settings,
        notifier=notifier,
    )


@router.post("/claim/photos", response_model=ClaimResponse)
async def claim_with_photos(
    farmer_id: Annotated[str, Form()],
    crop: Annotated[str, Form()],
    event_date: Annotated[str, Form()],
    event: Annotated[str, Form()] = "hail",
    device_lat: Annotated[float | None, Form()] = None,
    device_lon: Annotated[float | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
    repo: Repository = Depends(repo_dep),
    web: WebClient = Depends(web_dep),
    settings: Settings = Depends(settings_dep),
    notifier: Notifier = Depends(notifier_dep),
) -> ClaimResponse:
    """Upload the photos: capture time and GPS are read from their EXIF data and checked against the event.
    The files are inspected in memory and not stored."""
    if event not in EVENTS:
        raise HTTPException(422, f"event must be one of {sorted(EVENTS)}")
    uploads = files or []
    if len(uploads) > MAX_PHOTOS:
        raise HTTPException(413, f"at most {MAX_PHOTOS} photos")
    photos: list[PhotoMeta] = []
    for f in uploads:
        data = await f.read(MAX_PHOTO_BYTES + 1)
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(413, f"{f.filename}: photo larger than {MAX_PHOTO_BYTES // 1024 // 1024} MB")
        meta = read_photo(f.filename or "photo", data)
        if device_lat is not None and device_lon is not None:
            meta = replace(meta, device_lat=device_lat, device_lon=device_lon)
        photos.append(meta)
    return await _run_claim(
        farmer_id=farmer_id, crop=crop, event=event, event_date=event_date, photos=photos,
        repo=repo, web=web, settings=settings, notifier=notifier,
    )
