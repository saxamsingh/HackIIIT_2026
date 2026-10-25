"""PDF reports: a prefilled scheme packet and a claim dossier. Jinja renders a small text markup, ReportLab
lays it out. Both carry the banner "Farmer verifies and submits" and are drafts, never submissions.

The PDFs are English only: ReportLab's built-in fonts have no Devanagari, and bundling a font was left for
a later change rather than downloading one unasked."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from ..config import Settings
from ..models import Farmer
from ..rules.eligibility import DOCUMENT_LABELS, Eligibility
from ..schemes import Scheme

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(enabled_extensions=("j2",)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


def _slug(text: str) -> str:
    return _SAFE.sub("-", text).strip("-")[:60] or "file"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=18, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=3),
        "p": ParagraphStyle("p", parent=base["BodyText"], fontSize=10, leading=13),
        "li": ParagraphStyle("li", parent=base["BodyText"], fontSize=10, leading=13, leftIndent=12, bulletIndent=2),
        "banner": ParagraphStyle(
            "banner", parent=base["BodyText"], fontSize=10, leading=13, backColor=colors.HexColor("#fff3cd"),
            borderPadding=5, textColor=colors.HexColor("#5c4400"), spaceAfter=6,
        ),
    }


def _flowables(markup: str) -> list[Any]:
    """`# h1`, `## h2`, `- bullet` and plain lines (Jinja has already escaped & < >)."""
    styles = _styles()
    out: list[Any] = []
    for raw in markup.splitlines():
        line = raw.rstrip()
        if not line:
            out.append(Spacer(1, 3))
        elif line.startswith("## "):
            out.append(Paragraph(line[3:], styles["h2"]))
        elif line.startswith("# "):
            out.append(Paragraph(line[2:], styles["h1"]))
        elif line.startswith("- "):
            out.append(Paragraph(line[2:], styles["li"], bulletText="•"))
        elif line.startswith("Farmer verifies"):
            out.append(Paragraph(f"<b>{line}</b>", styles["banner"]))
        else:
            out.append(Paragraph(line, styles["p"]))
    return out


def _write_pdf(path: Path, markup: str, title: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=title, author="KhetKaaj",
    )
    doc.build(_flowables(markup))
    return path


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def packet_name(farmer: Farmer, scheme: Scheme) -> str:
    return f"packet-{_slug(farmer.id)}-{_slug(scheme.id)}.pdf"


def render_packet(farmer: Farmer, scheme: Scheme, result: Eligibility, settings: Settings, mode: str) -> str:
    """Write the prefilled draft packet and return its file name (served at /files/<name>)."""
    markup = _env.get_template("packet.txt.j2").render(
        farmer=farmer,
        scheme=scheme,
        reasons=result.reasons,
        documents=[
            {"label": DOCUMENT_LABELS.get(d, d), "have": d in farmer.documents} for d in scheme.requires_documents
        ],
        generated=_stamp(),
        mode=mode,
    )
    name = packet_name(farmer, scheme)
    _write_pdf(settings.files_dir / name, markup, f"{scheme.name} - draft packet")
    return name


def dossier_name(claim_id: str) -> str:
    return f"dossier-{_slug(claim_id)}.pdf"


def render_dossier(settings: Settings, mode: str, **fields: Any) -> str:
    """Write the claim dossier and return its file name. `fields` are the template variables."""
    markup = _env.get_template("dossier.txt.j2").render(generated=_stamp(), mode=mode, **fields)
    name = dossier_name(fields["claim_id"])
    _write_pdf(settings.files_dir / name, markup, f"Claim dossier {fields['claim_id']}")
    return name
