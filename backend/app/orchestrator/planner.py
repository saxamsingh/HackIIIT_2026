"""Planner: triage a message, run the right agent, pass the result through the safety gate.

The gate is always the last step. There is deliberately no path from an agent to a farmer that skips it.
After the gate, a sell or subsidy answer that carries a ledger value is recorded as a projected entry.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from importlib import import_module
from typing import Any

from .. import ledger
from ..agents import stubs
from ..agents.base import AgentContext
from ..channels.notify import Notifier
from ..config import Settings
from ..db import Repository
from ..models import AgentName, AgentResult, GatedResponse, Triage
from ..replies import MENU
from ..safety import gate
from ..tinyfish import WebClient
from .triage import triage as run_triage

log = logging.getLogger("khetkaaj.planner")

_STUBS: dict[AgentName, Callable[[AgentContext], AgentResult]] = {
    "sell": lambda c: stubs.sell(c.triage.crop, c.triage.quantity_qtl),
    "subsidy": lambda c: stubs.subsidy(c.triage.crop),
    "claim": lambda c: stubs.claim(c.triage.crop),
    "watch": lambda c: stubs.watch(),
}

_INTENT_TO_AGENT: dict[str, AgentName] = {"sell": "sell", "subsidy": "subsidy", "claim": "claim"}
_LEDGER_KIND = {"sell": "sell", "subsidy": "subsidy"}


async def run_agent(name: AgentName, ctx: AgentContext) -> AgentResult:
    """Call the real agent module; fall back to its stub while the module is still NotImplemented."""
    module = import_module(f"app.agents.{name}")
    runner: Callable[[AgentContext], Awaitable[AgentResult]] = module.run
    try:
        return await runner(ctx)
    except NotImplementedError:
        log.info("agent '%s' not implemented yet, using its stub", name)
        return _STUBS[name](ctx)


def _record_ledger(gated: GatedResponse, repo: Repository, farmer_id: str | None) -> GatedResponse:
    """Project the answer's money value into the ledger (once per question) and tell the caller which entry."""
    kind = _LEDGER_KIND.get(gated.agent or "")
    if gated.status != "answered" or not farmer_id or kind is None:
        return gated
    amount, formula = gated.data.get("ledger_value_rs"), gated.data.get("formula")
    if not isinstance(amount, int | float) or not isinstance(formula, str):
        return gated
    entry = ledger.project(repo, farmer_id, kind, float(amount), formula)  # type: ignore[arg-type]
    if entry is None:
        return gated
    return gated.model_copy(update={"data": {**gated.data, "ledger_entry_id": entry.id}})


async def respond(
    text: str,
    *,
    repo: Repository,
    web: WebClient,
    settings: Settings,
    farmer_id: str | None = None,
    forced: Triage | None = None,
    extra: dict[str, Any] | None = None,
    notifier: Notifier | None = None,
) -> GatedResponse:
    """The whole pipeline for one message. `forced` lets a typed route (POST /api/sell) skip keyword triage."""
    tri = forced or run_triage(text)
    if tri.intent == "unknown":
        return GatedResponse(status="menu", language=tri.language, intent="unknown", reply=MENU[tri.language])

    result: AgentResult | None = None
    agent = _INTENT_TO_AGENT.get(tri.intent)
    if agent is not None:  # advisory has no agent: it goes straight to the gate and is handed to a human
        farmer = repo.get_farmer(farmer_id) if farmer_id else None
        ctx = AgentContext(
            triage=tri, farmer=farmer, repo=repo, web=web, settings=settings, notifier=notifier, extra=extra or {}
        )
        result = await run_agent(agent, ctx)
    gated = gate(tri, result, repo, settings, farmer_id)
    return _record_ledger(gated, repo, farmer_id)
