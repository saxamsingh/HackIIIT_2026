"""Writes every TinyFish call to the runs table, so the live viewer, the audit trail and cost reports share
one source. A tracker with no repository is a no-op (scripts and unit tests that do not need history)."""

from __future__ import annotations

from typing import Any, Literal

from ..db import Repository
from ..models import RunRecord, TinyFishKind, now
from .base import AgentEvent

Mode = Literal["live", "replay"]


class RunTracker:
    def __init__(self, repo: Repository | None, mode: Mode) -> None:
        self.repo = repo
        self.mode = mode

    def begin(self, kind: TinyFishKind, target: str, run_id: str, status: str = "RUNNING") -> None:
        if self.repo is None:
            return
        self.repo.save_run(
            RunRecord(id=run_id, kind=kind, status=status, target=target[:500], mode=self.mode)  # type: ignore[arg-type]
        )

    def event(self, run_id: str, event: AgentEvent) -> None:
        """Apply one SSE event. `streaming_url` is stored the moment it arrives, before the run finishes."""
        if self.repo is None:
            return
        if event.type == "STREAMING_URL" and event.streaming_url:
            self.repo.update_run(run_id, streaming_url=event.streaming_url)
        elif event.type == "PROGRESS":
            run = self.repo.get_run(run_id)
            self.repo.update_run(run_id, steps=(run.steps or 0) + 1 if run else 1)

    def finish(
        self,
        run_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        steps: int | None = None,
        streaming_url: str | None = None,
        video_url: str | None = None,
        cost_credits: float | None = None,
    ) -> None:
        if self.repo is None:
            return
        fields: dict[str, Any] = {"status": status, "result": result, "error": error}
        for key, value in (
            ("steps", steps), ("streaming_url", streaming_url), ("video_url", video_url),
            ("cost_credits", cost_credits),
        ):
            if value is not None:
                fields[key] = value
        self.repo.update_run(run_id, **fields)

    def simple(self, kind: TinyFishKind, target: str, run_id: str, *, ok: bool, error: str | None = None) -> None:
        """One-shot calls (search, fetch): record start and end together."""
        if self.repo is None:
            return
        self.repo.save_run(
            RunRecord(
                id=run_id, kind=kind, status="COMPLETED" if ok else "FAILED", target=target[:500],
                error=None if ok else {"message": error or "failed", "category": "UNKNOWN"},
                mode=self.mode, updated_at=now(),  # type: ignore[arg-type]
            )
        )
