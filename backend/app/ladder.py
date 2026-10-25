"""The ladder: try the cheap rung first, escalate only when it cannot answer.

Rung 1 is Fetch (render the page, parse it with deterministic code). Rung 2 is an Agent run with an
`output_schema`, for pages that need interaction (a form, a district picker). Which rung answered is
logged and returned, so cost and reliability can be reported. CLAUDE.md section 6.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from .models import Evidence, EvidenceKind
from .tinyfish import BudgetExceeded, FetchedPage, OnEvent, WebClient, WebClientError

log = logging.getLogger("khetkaaj.ladder")
T = TypeVar("T")


@dataclass
class LadderResult(Generic[T]):
    data: T
    rung: Literal["fetch", "agent"]
    url: str
    kind: EvidenceKind  # "replay" when the web client is replaying fixtures, so a cached answer never looks live
    run_id: str | None = None

    def evidence(self, *, title: str | None = None, quote: str | None = None) -> Evidence:
        return Evidence(source_url=self.url, kind=self.kind, title=title, quote=quote, run_id=self.run_id)


async def fetch_then_agent(
    web: WebClient,
    *,
    url: str,
    parse_page: Callable[[FetchedPage], T | None],
    goal: str,
    output_schema: dict[str, Any],
    parse_agent: Callable[[dict[str, Any]], T | None],
    purpose: str | None = None,
    fresh: bool = False,
    on_event: OnEvent | None = None,
) -> LadderResult[T] | None:
    """Return the parsed data and the rung that produced it, or None when neither rung could."""
    replay = web.mode == "replay"

    try:
        fetched = await web.fetch([url], purpose=purpose, fresh=fresh)
        for page in fetched.results:
            if page.text and (data := parse_page(page)) is not None:
                log.info("ladder: fetch answered url=%s", url)
                return LadderResult(data, "fetch", page.final_url or page.url, "replay" if replay else "fetch")
        log.info("ladder: fetch could not answer url=%s, escalating to the agent", url)
    except BudgetExceeded:
        raise
    except WebClientError as e:
        log.info("ladder: fetch failed url=%s (%s), escalating to the agent", url, e)

    run = await web.run_agent(url, goal, output_schema, on_event=on_event)
    if run.status != "COMPLETED" or not run.result:
        log.warning("ladder: agent run %s ended %s", run.run_id, run.status)
        return None
    data = parse_agent(run.result)
    if data is None:
        log.warning("ladder: agent run %s returned a result the parser could not use", run.run_id)
        return None
    log.info("ladder: agent answered url=%s run=%s", url, run.run_id)
    return LadderResult(data, "agent", url, "replay" if replay else "agent", run.run_id)
