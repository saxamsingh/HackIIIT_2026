"""Scheme eligibility: a deterministic matcher over the YAML rules. No model decides who qualifies.

Three outcomes: `eligible`, `ineligible` (a rule failed) and `needs_info` (a rule depends on something the
farmer profile does not hold, such as age). Missing documents do not make a farmer ineligible; they are
reported separately so the packet can list what to collect."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..models import Farmer
from ..schemes import Scheme

KNOWN_FACTS = frozenset({"state", "district", "land_acres", "category", "crops"})
DOCUMENT_LABELS = {
    "aadhaar": "Aadhaar card",
    "bank_passbook": "Bank passbook (account linked to Aadhaar)",
    "land_record": "Land record (khatauni / khasra)",
    "farmer_id": "Farmer ID",
    "mobile_linked_aadhaar": "Mobile number linked to Aadhaar (for OTP e-KYC)",
}


@dataclass
class Eligibility:
    status: Literal["eligible", "ineligible", "needs_info"]
    reasons: list[str] = field(default_factory=list)
    missing_docs: list[str] = field(default_factory=list)
    needs_info: list[str] = field(default_factory=list)

    @property
    def eligible(self) -> bool:
        return self.status == "eligible"


def evaluate(farmer: Farmer, scheme: Scheme) -> Eligibility:
    rules = scheme.eligibility
    reasons: list[str] = []
    failed = False
    unknown: list[str] = []

    def check(ok: bool, yes: str, no: str) -> None:
        nonlocal failed
        reasons.append(yes if ok else no)
        failed = failed or not ok

    for key, value in rules.items():
        if key == "states":
            if value:
                check(
                    farmer.state.lower() in {s.lower() for s in value},
                    f"Available in {farmer.state}",
                    f"Only for {', '.join(value)}; you are in {farmer.state}",
                )
        elif key == "categories":
            if value:
                check(
                    farmer.category in value,
                    f"Category '{farmer.category}' qualifies",
                    f"For {', '.join(value)} farmers; you are '{farmer.category}'",
                )
        elif key == "crops_any":
            if value:
                check(
                    bool(set(farmer.crops) & set(value)),
                    "You grow a covered crop",
                    f"For farmers growing {', '.join(value)}",
                )
        elif key == "land_required":
            if value:
                check(farmer.land_acres > 0, "You have farmland", "Needs farmland")
        elif key == "min_land_acres":
            check(
                farmer.land_acres >= value,
                f"Land {farmer.land_acres:g} acres meets the {value:g}-acre minimum",
                f"Needs at least {value:g} acres; you have {farmer.land_acres:g}",
            )
        elif key == "max_land_acres":
            check(
                farmer.land_acres <= value,
                f"Land {farmer.land_acres:g} acres is within the {value:g}-acre limit",
                f"Limited to {value:g} acres; you have {farmer.land_acres:g}",
            )
        else:  # a rule this matcher does not understand must never silently pass
            unknown.append(f"rule '{key}' is not supported")

    for fact in scheme.requires_facts:
        if fact not in KNOWN_FACTS:
            unknown.append(fact)

    missing = [d for d in scheme.requires_documents if d not in farmer.documents]
    if failed:
        return Eligibility("ineligible", reasons, missing, unknown)
    if unknown:
        return Eligibility("needs_info", reasons, missing, unknown)
    return Eligibility("eligible", reasons, missing, [])
