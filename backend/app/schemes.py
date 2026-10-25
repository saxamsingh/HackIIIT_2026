"""Scheme records (knowledge/schemes/*.yaml) and the human review gate.

A scheme is shown to a farmer only when `reviewed` is true, and only a person can make it so: the review
command records who and when. CLAUDE.md sections 2.6 and 7."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .config import Settings


class SchemeSource(BaseModel):
    url: str
    title: str = ""
    retrieved: str = ""


class Scheme(BaseModel):
    id: str
    name: str
    level: str = "central"
    benefit: str
    estimated_value_rs: float | None = None
    value_basis: str = ""
    apply_url: str
    url_verified: bool = False
    deadline: str | None = None  # ISO date, only ever from a cited source
    eligibility: dict[str, Any] = Field(default_factory=dict)
    requires_documents: list[str] = Field(default_factory=list)
    requires_facts: list[str] = Field(default_factory=list)
    fact_rules: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    sources: list[SchemeSource] = Field(default_factory=list)
    discovered: bool = False
    reviewed: bool = False
    reviewed_by: str | None = None
    reviewed_at: str | None = None


def schemes_dir(settings: Settings) -> Path:
    return settings.knowledge_dir / "schemes"


def load_schemes(settings: Settings, *, reviewed_only: bool = False) -> list[Scheme]:
    out: list[Scheme] = []
    for path in sorted(schemes_dir(settings).glob("*.yaml")):
        scheme = Scheme.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if scheme.reviewed or not reviewed_only:
            out.append(scheme)
    return out


def _path_for(settings: Settings, scheme_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", scheme_id):
        raise KeyError(scheme_id)
    path = schemes_dir(settings) / f"{scheme_id}.yaml"
    if not path.is_file():
        raise KeyError(scheme_id)
    return path


def _set_line(text: str, key: str, value: str) -> str:
    """Replace a top-level `key: ...` line in place, so comments in the file survive."""
    line = f"{key}: {value}"
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    return pattern.sub(line, text, count=1) if pattern.search(text) else text.rstrip("\n") + f"\n{line}\n"


def review_scheme(settings: Settings, scheme_id: str, reviewer: str, today: date | None = None) -> Scheme:
    """Mark a scheme reviewed by a named person. The name is mandatory: 'reviewed' must mean a human read it."""
    if not reviewer.strip():
        raise ValueError("a reviewer name is required")
    path = _path_for(settings, scheme_id)
    text = path.read_text(encoding="utf-8")
    text = _set_line(text, "reviewed", "true")
    text = _set_line(text, "reviewed_by", yaml.safe_dump(reviewer.strip(), default_flow_style=True).split("\n")[0])
    text = _set_line(text, "reviewed_at", f'"{(today or date.today()).isoformat()}"')
    path.write_text(text, encoding="utf-8")
    return Scheme.model_validate(yaml.safe_load(text))


def unreview_scheme(settings: Settings, scheme_id: str) -> Scheme:
    path = _path_for(settings, scheme_id)
    text = path.read_text(encoding="utf-8")
    for key, value in (("reviewed", "false"), ("reviewed_by", "null"), ("reviewed_at", "null")):
        text = _set_line(text, key, value)
    path.write_text(text, encoding="utf-8")
    return Scheme.model_validate(yaml.safe_load(text))


def save_discovered(settings: Settings, scheme: Scheme) -> Path | None:
    """Write a newly discovered scheme, never overwriting an existing record (a reviewed one in particular)."""
    path = schemes_dir(settings) / f"{scheme.id}.yaml"
    if path.exists():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = scheme.model_dump(mode="json")
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path
