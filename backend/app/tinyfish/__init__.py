"""Web access for agents: TinyFish live, or recorded fixtures offline."""

from __future__ import annotations

from ..config import Settings
from ..db import Repository
from .base import (
    AgentEvent,
    AgentRunResult,
    BudgetExceeded,
    FetchedPage,
    FetchResponse,
    FixtureMissing,
    OnEvent,
    SearchResponse,
    WebClient,
    WebClientError,
    emit,
)
from .budget import BudgetGuard
from .cache import DiskCache
from .live import TinyFishClient, looks_blocked
from .replay import ReplayClient, load_monitor_fixture


def make_web_client(settings: Settings, repo: Repository | None = None) -> WebClient:
    """Live or replay, per TINYFISH_MODE. Pass the repository so every call is written to the runs table."""
    if settings.tinyfish_mode == "live":
        return TinyFishClient(
            settings,
            BudgetGuard(settings.tinyfish_budget_agent_runs, settings.tinyfish_budget_free_calls),
            DiskCache(settings.cache_dir, settings.tinyfish_cache_ttl_seconds),
            repo,
        )
    return ReplayClient(settings.tinyfish_fixtures_dir, repo=repo, district=settings.demo_district)


__all__ = [
    "AgentEvent",
    "AgentRunResult",
    "BudgetExceeded",
    "BudgetGuard",
    "DiskCache",
    "FetchResponse",
    "FetchedPage",
    "FixtureMissing",
    "OnEvent",
    "ReplayClient",
    "SearchResponse",
    "TinyFishClient",
    "WebClient",
    "WebClientError",
    "emit",
    "load_monitor_fixture",
    "looks_blocked",
    "make_web_client",
]
