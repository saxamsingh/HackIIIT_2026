"""Turn an inbound TinyFish webhook into database updates. The router only authenticates and dispatches."""

from __future__ import annotations

import logging
from typing import Any

from .db import Repository
from .models import RunRecord

log = logging.getLogger("khetkaaj.webhooks")
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def is_run_webhook(body: dict[str, Any]) -> bool:
    """`{event: run.completed|run.failed|run.cancelled, run_id, status, data: <GET /v1/runs/{id}>}`."""
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    run_id = body.get("run_id") or data.get("run_id")
    status = body.get("status") or data.get("status")
    return bool(run_id) and status in TERMINAL and "monitor" not in body


def apply_run_webhook(repo: Repository, body: dict[str, Any]) -> str:
    """Record the final state of a run we may or may not have seen start (the stream can drop)."""
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    run_id = str(body.get("run_id") or data.get("run_id"))
    status = str(body.get("status") or data.get("status"))
    existing = repo.get_run(run_id)
    if existing is None:
        existing = repo.save_run(
            RunRecord(
                id=run_id,
                kind="agent",
                status="RUNNING",
                target=str(data.get("goal") or "(from webhook)"),
                mode="live",
            )
        )
    steps = data.get("num_of_steps") or (len(data["steps"]) if isinstance(data.get("steps"), list) else None)
    repo.update_run(
        run_id,
        status=status,
        result=data.get("result"),
        error=data.get("error"),
        streaming_url=data.get("streaming_url") or existing.streaming_url,
        steps=steps or existing.steps,
    )
    return run_id


def monitor_payload(body: dict[str, Any]) -> dict[str, Any] | None:
    """The `{monitor, run}` object inside a monitor webhook, whether it is nested under `data` or not.

    The real envelope is unconfirmed (CLAUDE.md section 6), so both shapes are accepted."""
    inner = body.get("data") if isinstance(body.get("data"), dict) and "run" in body["data"] else body
    if isinstance(inner.get("run"), dict) and "results" in inner["run"]:
        return inner
    return None
