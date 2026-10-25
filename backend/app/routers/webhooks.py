"""Inbound webhooks and the offline monitor replay used by the demo."""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import webhooks
from ..agents import watch
from ..channels.notify import Notifier
from ..config import Settings
from ..db import Repository
from ..deps import notifier_dep, repo_dep, settings_dep, web_dep
from ..models import Alert, ReplayMonitorRequest
from ..tinyfish import FixtureMissing, WebClient, load_monitor_fixture

router = APIRouter()
log = logging.getLogger("khetkaaj.webhooks")


@router.post("/webhooks/tinyfish")
async def tinyfish_webhook(
    request: Request,
    token: str = "",
    settings: Settings = Depends(settings_dep),
    repo: Repository = Depends(repo_dep),
    web: WebClient = Depends(web_dep),
    notifier: Notifier = Depends(notifier_dep),
) -> dict[str, Any]:
    """TinyFish does not sign webhooks, so the secret rides in the URL: /webhooks/tinyfish?token=...

    With TINYFISH_WEBHOOK_TOKEN unset the endpoint accepts anything, which is only fit for local development.
    A run webhook updates the runs table; a monitor webhook goes to the Watch agent.
    """
    expected = settings.tinyfish_webhook_token
    if expected and not hmac.compare_digest(token, expected):
        raise HTTPException(403, "invalid webhook token")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(422, "expected a JSON object")

    if webhooks.is_run_webhook(body):
        return {"ok": True, "handled": "run", "run_id": webhooks.apply_run_webhook(repo, body)}
    payload = webhooks.monitor_payload(body)
    if payload is not None:
        alerts = await watch.handle_monitor_payload(
            payload, repo=repo, web=web, settings=settings, notifier=notifier
        )
        return {"ok": True, "handled": "monitor", "alerts": [a.id for a in alerts]}
    log.warning("unrecognised TinyFish webhook shape: keys=%s", sorted(body)[:10])
    return {"ok": True, "handled": "ignored"}


@router.post("/demo/replay-monitor", response_model=Alert)
async def replay_monitor(
    body: ReplayMonitorRequest,
    settings: Settings = Depends(settings_dep),
    repo: Repository = Depends(repo_dep),
    web: WebClient = Depends(web_dep),
    notifier: Notifier = Depends(notifier_dep),
) -> Alert:
    """Replay a recorded Monitor run as if it had just fired, so the alert path works with Wi-Fi off.

    One alert is created per farmer in the demo district; the first is returned and all are listed by
    GET /api/alerts."""
    try:
        payload = load_monitor_fixture(settings.tinyfish_fixtures_dir, body.fixture_name, settings.demo_district)
    except FixtureMissing as e:
        raise HTTPException(404, str(e)) from None
    alerts = await watch.handle_monitor_payload(
        payload, repo=repo, web=web, settings=settings, notifier=notifier
    )
    if not alerts:
        raise HTTPException(409, "the replayed run raised no alert (nothing changed, or no farmers in the district)")
    return alerts[0]
