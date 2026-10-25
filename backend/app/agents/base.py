"""What every agent receives. Agents reach the web only through `ctx.web` (a WebClient)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..channels.notify import Notifier
from ..config import Settings
from ..db import Repository
from ..models import Farmer, Triage
from ..tinyfish import WebClient


@dataclass
class AgentContext:
    triage: Triage
    farmer: Farmer | None
    repo: Repository
    web: WebClient
    settings: Settings
    notifier: Notifier | None = None
    # Typed inputs a route passes alongside the triage (a claim's event, date and photo metadata).
    extra: dict[str, Any] = field(default_factory=dict)
