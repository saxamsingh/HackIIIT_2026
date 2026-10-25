"""Budget guard: a hard cap on what one server process may spend, checked before every live call."""

from __future__ import annotations

from threading import Lock

from ..models import TinyFishKind
from .base import BudgetExceeded


class BudgetGuard:
    """Agent runs cost credits, so they get their own small cap. Search, fetch and monitor calls share a
    larger one that mostly protects against a runaway loop."""

    def __init__(self, max_agent_runs: int, max_free_calls: int) -> None:
        self.max_agent_runs = max_agent_runs
        self.max_free_calls = max_free_calls
        self.agent_runs = 0
        self.free_calls = 0
        self._lock = Lock()

    def charge(self, kind: TinyFishKind) -> None:
        """Count one call, or raise BudgetExceeded without counting it."""
        with self._lock:
            if kind == "agent":
                if self.agent_runs >= self.max_agent_runs:
                    raise BudgetExceeded(f"agent run budget of {self.max_agent_runs} is spent")
                self.agent_runs += 1
            else:
                if self.free_calls >= self.max_free_calls:
                    raise BudgetExceeded(f"search/fetch budget of {self.max_free_calls} is spent")
                self.free_calls += 1

    def usage(self) -> dict[str, int]:
        return {
            "agent_runs": self.agent_runs,
            "max_agent_runs": self.max_agent_runs,
            "free_calls": self.free_calls,
            "max_free_calls": self.max_free_calls,
        }
