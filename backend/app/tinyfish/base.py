"""The only interface agents use to reach the web. Agents never import the TinyFish SDK directly.

Shapes mirror the `tinyfish` SDK (0.11) models, trimmed to the fields KhetKaaj reads, so a recorded live
response drops straight into a replay fixture. See CLAUDE.md section 6.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class WebClientError(Exception):
    """Base class for everything the web layer raises."""


class BudgetExceeded(WebClientError):
    """A call was refused because the process budget is spent. Nothing was sent to TinyFish."""


class FixtureMissing(WebClientError):
    """Replay mode has no fixture for this request. Record one with TINYFISH_RECORD=1."""


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SearchHit(_Lenient):
    position: int = 0
    title: str
    url: str
    snippet: str = ""
    site_name: str = ""
    date: str | None = None


class SearchResponse(_Lenient):
    query: str
    results: list[SearchHit] = Field(default_factory=list)
    total_results: int = 0
    page: int = 0


class FetchedPage(_Lenient):
    url: str
    final_url: str | None = None
    title: str | None = None
    text: str | None = None
    format: Literal["markdown", "html", "json"] = "markdown"
    links: list[str] = Field(default_factory=list)


class FetchFailure(_Lenient):
    url: str
    error: str


class FetchResponse(_Lenient):
    results: list[FetchedPage] = Field(default_factory=list)
    errors: list[FetchFailure] = Field(default_factory=list)


EventTypeName = Literal["STARTED", "STREAMING_URL", "PROGRESS", "HEARTBEAT", "COMPLETE"]


class AgentEvent(_Lenient):
    """One server-sent event of an Agent run. The SDK calls the COMPLETE payload `result_json`, the
    REST docs call it `result`; both are accepted."""

    type: EventTypeName
    run_id: str | None = None
    streaming_url: str | None = None
    purpose: str | None = None
    status: str | None = None
    result: dict[str, Any] | None = Field(
        default=None, validation_alias=AliasChoices("result", "result_json")
    )
    error: dict[str, Any] | None = None
    timestamp: datetime | None = None


class AgentRunResult(_Lenient):
    run_id: str | None = None
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
    streaming_url: str | None = None
    video_url: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    num_of_steps: int | None = None
    events: list[AgentEvent] = Field(default_factory=list)


OnEvent = Callable[[AgentEvent], Awaitable[None] | None]


async def emit(on_event: OnEvent | None, event: AgentEvent) -> None:
    """Call a sync or async event callback, if there is one."""
    if on_event is None:
        return
    maybe = on_event(event)
    if asyncio.iscoroutine(maybe):
        await maybe


class WebClient(Protocol):
    """Search, Fetch, Agent. `mode` is "live" or "replay" and is shown to the user, never hidden."""

    mode: Literal["live", "replay"]

    async def search(self, query: str, *, purpose: str | None = None) -> SearchResponse: ...

    async def fetch(
        self, urls: list[str], *, purpose: str | None = None, fresh: bool = False
    ) -> FetchResponse: ...

    async def run_agent(
        self,
        url: str,
        goal: str,
        output_schema: dict[str, Any] | None = None,
        *,
        on_event: OnEvent | None = None,
    ) -> AgentRunResult: ...
