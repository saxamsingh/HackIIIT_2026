"""ReplayClient: answers from recorded fixtures, so the whole demo runs with Wi-Fi off.

A fixture is one JSON file in backend/fixtures/tinyfish/:
    {"kind": "search|fetch|agent|monitor", "default": true?, "request": {...}, "response": {...}}
A request matches a fixture on its canonical key (see `_match_key`); with no exact match the kind's
`default` fixture answers, so a demo question the team did not record still returns something.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..db import Repository
from ..models import new_id
from .base import (
    AgentRunResult,
    FetchResponse,
    FixtureMissing,
    OnEvent,
    SearchResponse,
    emit,
)
from .runs import RunTracker


@dataclass(frozen=True)
class Fixture:
    kind: str
    request: dict[str, Any]
    response: dict[str, Any]
    default: bool
    path: Path


def _match_key(kind: str, request: dict[str, Any]) -> str:
    if kind == "search":
        parts: Any = request.get("query", "").strip().lower()
    elif kind == "fetch":
        parts = sorted(request.get("urls", []))
    elif kind == "agent":
        parts = [request.get("url", ""), request.get("goal", "").strip().lower()]
    else:
        parts = request.get("fixture_name", "")
    return json.dumps(parts, ensure_ascii=False)


def load_fixtures(directory: Path, district: str | None = None) -> list[Fixture]:
    """`{district}` in a fixture is replaced by the configured demo district, so a recorded warning always
    names the district the demo is set up for."""
    fixtures: list[Fixture] = []
    for path in sorted(directory.glob("*.json")):
        raw = path.read_text(encoding="utf-8")
        if district:
            raw = raw.replace("{district}", district)
        doc = json.loads(raw)
        fixtures.append(
            Fixture(doc["kind"], doc.get("request", {}), doc["response"], bool(doc.get("default")), path)
        )
    return fixtures


_CONTAINS_KEYS = ("query_contains", "url_contains")


def _is_pattern(fx: Fixture) -> bool:
    return any(k in fx.request for k in _CONTAINS_KEYS)


def _pattern_matches(fx: Fixture, kind: str, request: dict[str, Any]) -> bool:
    """A fixture may answer a family of requests: `query_contains` for search, `url_contains` for fetch."""
    if kind == "search" and "query_contains" in fx.request:
        return fx.request["query_contains"].lower() in request.get("query", "").lower()
    if kind == "fetch" and "url_contains" in fx.request:
        return any(fx.request["url_contains"] in u for u in request.get("urls", []))
    return False


def load_monitor_fixture(directory: Path, name: str, district: str | None = None) -> dict[str, Any]:
    """The recorded Monitor run for `name` (used by POST /demo/replay-monitor)."""
    for fx in load_fixtures(directory, district):
        if fx.kind == "monitor" and fx.request.get("fixture_name") == name:
            return fx.response
    raise FixtureMissing(f"no monitor fixture named '{name}' in {directory}")


class ReplayClient:
    mode: Literal["live", "replay"] = "replay"

    def __init__(
        self,
        directory: Path,
        event_delay: float = 0.0,
        repo: Repository | None = None,
        district: str | None = None,
    ) -> None:
        self.directory = directory
        self.event_delay = event_delay
        self.tracker = RunTracker(repo, "replay")
        self._fixtures = load_fixtures(directory, district)

    def _find(self, kind: str, request: dict[str, Any]) -> Fixture:
        of_kind = [f for f in self._fixtures if f.kind == kind]
        key = _match_key(kind, request)
        for fx in of_kind:  # an exact recording of this request wins
            if not _is_pattern(fx) and _match_key(kind, fx.request) == key:
                return fx
        for fx in of_kind:  # then a fixture that answers a family of requests
            if _pattern_matches(fx, kind, request):
                return fx
        for fx in of_kind:  # then the kind's default
            if fx.default:
                return fx
        raise FixtureMissing(f"no '{kind}' fixture for {request!r} in {self.directory}")

    async def search(self, query: str, *, purpose: str | None = None) -> SearchResponse:
        found = SearchResponse.model_validate(self._find("search", {"query": query}).response)
        self.tracker.simple("search", query, new_id("run"), ok=True)
        return found

    async def fetch(
        self, urls: list[str], *, purpose: str | None = None, fresh: bool = False
    ) -> FetchResponse:
        pages = FetchResponse.model_validate(self._find("fetch", {"urls": urls}).response)
        self.tracker.simple("fetch", ",".join(urls), new_id("run"), ok=True)
        return pages

    async def run_agent(
        self,
        url: str,
        goal: str,
        output_schema: dict[str, Any] | None = None,
        *,
        on_event: OnEvent | None = None,
    ) -> AgentRunResult:
        response = self._find("agent", {"url": url, "goal": goal}).response
        recorded = AgentRunResult.model_validate(response)
        # Each replay is its own run row, so repeated demos do not overwrite one another.
        run_id = new_id("run")
        events = [e.model_copy(update={"run_id": run_id}) for e in recorded.events]
        self.tracker.begin("agent", goal, run_id)
        for event in events:
            self.tracker.event(run_id, event)
            await emit(on_event, event)
            if self.event_delay:
                await asyncio.sleep(self.event_delay)
        result = recorded.model_copy(update={"run_id": run_id, "events": events})
        self.tracker.finish(
            run_id,
            result.status,
            result=result.result,
            error=result.error,
            steps=result.num_of_steps,
            streaming_url=result.streaming_url,
            video_url=result.video_url,
        )
        return result
