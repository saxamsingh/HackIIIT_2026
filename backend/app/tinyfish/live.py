"""TinyFishClient: the live WebClient over the official async SDK (`tinyfish` 0.11, CLAUDE.md section 6).

Rules kept here, because every agent depends on them:
- the budget guard is charged before every network call (a cache hit is free);
- at most `tinyfish_max_concurrent_runs` Agent runs at once, the rest queue;
- `streaming_url` is written to the runs table the moment its event arrives;
- a dropped stream is recovered by polling `runs.get` until the run is terminal;
- a run that finished COMPLETED but says the site blocked it is turned into a failure;
- TINYFISH_RECORD=1 saves each response as a replay fixture.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import ValidationError

from ..config import Settings
from ..db import Repository
from ..models import new_id
from .base import (
    AgentEvent,
    AgentRunResult,
    FetchResponse,
    OnEvent,
    SearchResponse,
    WebClientError,
    emit,
)
from .budget import BudgetGuard
from .cache import DiskCache
from .recorder import record_fixture
from .runs import RunTracker

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
_BLOCK_PHRASES = (
    "captcha", "access denied", "blocked", "bot detection", "unusual traffic", "verify you are human",
    "cloudflare", "forbidden",
)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list | tuple):
        return [s for v in value for s in _strings(v)]
    return []


def looks_blocked(result: dict[str, Any] | None) -> bool:
    """A COMPLETED run can still be a failure: the agent reached a CAPTCHA or an access-denied page."""
    if not result:
        return False
    if result.get("blocked") is True or result.get("is_blocked") is True:
        return True
    text = " ".join(_strings(result)).lower()
    return any(phrase in text for phrase in _BLOCK_PHRASES)


def _status(value: Any) -> str:
    return str(getattr(value, "value", value))


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else dict(model)


def to_event(raw: Any) -> AgentEvent | None:
    """An SDK stream item as our AgentEvent, or None for an event type we do not model."""
    try:
        return AgentEvent.model_validate(_dump(raw))
    except (ValidationError, TypeError, ValueError):
        return None


class TinyFishClient:
    mode: Literal["live", "replay"] = "live"
    poll_interval = 2.0  # seconds between runs.get polls after a dropped stream
    poll_timeout = 300.0

    def __init__(
        self,
        settings: Settings,
        budget: BudgetGuard,
        cache: DiskCache,
        repo: Repository | None = None,
        sdk: Any = None,
    ) -> None:
        if not settings.tinyfish_api_key and sdk is None:
            raise WebClientError("TINYFISH_MODE=live needs TINYFISH_API_KEY")
        self.settings = settings
        self.budget = budget
        self.cache = cache
        self.tracker = RunTracker(repo, "live")
        self._sdk = sdk
        self._run_slots = asyncio.Semaphore(max(1, settings.tinyfish_max_concurrent_runs))

    @property
    def sdk(self) -> Any:
        """The SDK client, created on first use so importing this module never needs a key."""
        if self._sdk is None:
            from tinyfish import AsyncTinyFish  # the PyPI SDK, not this package

            self._sdk = AsyncTinyFish(api_key=self.settings.tinyfish_api_key)
        return self._sdk

    def _record(self, kind: str, request: dict[str, Any], response: dict[str, Any]) -> None:
        if self.settings.tinyfish_record:
            record_fixture(self.settings.tinyfish_fixtures_dir, kind, request, response)

    # --- search and fetch ---------------------------------------------------------------------------------
    async def search(self, query: str, *, purpose: str | None = None) -> SearchResponse:
        request = {"query": query}
        cached = self.cache.get("search", request)
        if cached is not None:
            return SearchResponse.model_validate(cached)
        self.budget.charge("search")
        run_id = new_id("run")
        try:
            data = _dump(await self.sdk.search.query(query, purpose=purpose))
        except Exception as e:
            self.tracker.simple("search", query, run_id, ok=False, error=type(e).__name__)
            raise WebClientError(f"TinyFish search failed: {type(e).__name__}: {str(e)[:200]}") from e
        self.tracker.simple("search", query, run_id, ok=True)
        self.cache.put("search", request, data)
        self._record("search", request, data)
        return SearchResponse.model_validate(data)

    async def fetch(
        self, urls: list[str], *, purpose: str | None = None, fresh: bool = False
    ) -> FetchResponse:
        request = {"urls": urls}
        if not fresh:
            cached = self.cache.get("fetch", request)
            if cached is not None:
                return FetchResponse.model_validate(cached)
        self.budget.charge("fetch")
        run_id = new_id("run")
        extra = {"ttl": 0} if fresh else {}
        try:
            data = _dump(await self.sdk.fetch.get_contents(urls, purpose=purpose, **extra))
        except Exception as e:
            self.tracker.simple("fetch", ",".join(urls), run_id, ok=False, error=type(e).__name__)
            raise WebClientError(f"TinyFish fetch failed: {type(e).__name__}: {str(e)[:200]}") from e
        self.tracker.simple("fetch", ",".join(urls), run_id, ok=True)
        self.cache.put("fetch", request, data)
        self._record("fetch", request, data)
        return FetchResponse.model_validate(data)

    # --- agent runs ---------------------------------------------------------------------------------------
    async def run_agent(
        self,
        url: str,
        goal: str,
        output_schema: dict[str, Any] | None = None,
        *,
        on_event: OnEvent | None = None,
    ) -> AgentRunResult:
        self.budget.charge("agent")
        async with self._run_slots:  # TinyFish allows two concurrent runs; more wait here
            result = await self._run(url, goal, output_schema, on_event)
        if result.status == "COMPLETED":
            self._record(
                "agent",
                {"url": url, "goal": goal},
                {**result.model_dump(mode="json"), "events": [e.model_dump(mode="json") for e in result.events]},
            )
        return result

    async def _run(
        self, url: str, goal: str, output_schema: dict[str, Any] | None, on_event: OnEvent | None
    ) -> AgentRunResult:
        events: list[AgentEvent] = []
        run_id: str | None = None
        streaming_url: str | None = None
        final: AgentEvent | None = None
        try:
            async with self.sdk.agent.stream(goal=goal, url=url, output_schema=output_schema) as stream:
                async for raw in stream:
                    event = to_event(raw)
                    if event is None:
                        continue
                    if event.run_id and run_id is None:
                        run_id = event.run_id
                        self.tracker.begin("agent", goal, run_id)
                    events.append(event)
                    if run_id:
                        self.tracker.event(run_id, event)
                    if event.type == "STREAMING_URL":
                        streaming_url = event.streaming_url
                    if event.type == "COMPLETE":
                        final = event
                    await emit(on_event, event)
        except Exception as e:
            if run_id is None:
                raise WebClientError(
                    f"TinyFish agent run failed to start: {type(e).__name__}: {str(e)[:200]}"
                ) from e
            # SSE cannot resume: recover the outcome by polling the run until it is terminal.
            return self._finalise(await self._poll(run_id, events, streaming_url))

        if final is None:
            if run_id is None:
                raise WebClientError("TinyFish agent stream ended with no events")
            return self._finalise(await self._poll(run_id, events, streaming_url))
        return self._finalise(
            AgentRunResult(
                run_id=run_id,
                status=final.status or "COMPLETED",  # type: ignore[arg-type]
                streaming_url=streaming_url,
                result=final.result,
                error=final.error,
                num_of_steps=sum(1 for e in events if e.type == "PROGRESS"),
                events=events,
            )
        )

    async def _poll(
        self, run_id: str, events: list[AgentEvent], streaming_url: str | None
    ) -> AgentRunResult:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.poll_timeout
        while True:
            try:
                run = await self.sdk.runs.get(run_id)
            except Exception as e:
                raise WebClientError(f"polling TinyFish run {run_id} failed: {type(e).__name__}") from e
            status = _status(run.status)
            if status in TERMINAL:
                error = getattr(run, "error", None)
                return AgentRunResult(
                    run_id=run_id,
                    status=status,  # type: ignore[arg-type]
                    streaming_url=getattr(run, "streaming_url", None) or streaming_url,
                    result=getattr(run, "result", None),
                    error=_dump(error) if error else None,
                    num_of_steps=sum(1 for e in events if e.type == "PROGRESS") or None,
                    events=events,
                )
            if loop.time() > deadline:
                raise WebClientError(f"TinyFish run {run_id} did not finish within {self.poll_timeout:g}s")
            await asyncio.sleep(self.poll_interval)

    def _finalise(self, result: AgentRunResult) -> AgentRunResult:
        """Apply the COMPLETED-but-blocked rule, then write the outcome to the runs table."""
        if result.status == "COMPLETED" and looks_blocked(result.result):
            result = result.model_copy(
                update={
                    "status": "FAILED",
                    "result": None,
                    "error": {
                        "category": "AGENT_FAILURE",
                        "message": "The site blocked the agent (CAPTCHA or access denied).",
                    },
                }
            )
        if result.run_id:
            self.tracker.finish(
                result.run_id, result.status, result=result.result, error=result.error,
                steps=result.num_of_steps, streaming_url=result.streaming_url, video_url=result.video_url,
            )
        return result

    # --- monitors and wallet ------------------------------------------------------------------------------
    async def create_monitor(
        self,
        type_: Literal["fetch", "search"],
        config: dict[str, Any],
        schedule_cron: str,
        webhook_url: str | None = None,
        *,
        name: str | None = None,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        self.budget.charge("monitor")
        try:
            created = await self.sdk.monitors.create(
                type_, config, schedule_cron, name=name, webhook_url=webhook_url, purpose=purpose
            )
        except Exception as e:
            raise WebClientError(f"TinyFish monitor create failed: {type(e).__name__}: {str(e)[:200]}") from e
        return _dump(created)

    async def wallet_balance(self) -> float | None:
        """Available wallet balance, used by the smoke script to measure what a run cost."""
        try:
            return float((await self.sdk.wallet.get()).available_balance)
        except Exception:
            return None
