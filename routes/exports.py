"""Report export routes: CSV, Markdown, and standalone HTML."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from core.common.state import get_state
from core.engineering.power import analyze_power
from core.engineering.wiring import generate_wiring_plan
from core.reporting.bom import bom_table, ledger_table
from core.reporting.export import generate_html_report, generate_markdown_report

router = APIRouter(prefix="/api/export", tags=["Exports"])


@router.get("/{kind}")
def export(kind: str):
    state = get_state()
    b = state.active.get("build")
    req = state.active.get("requirements")
    if not b or not req:
        raise HTTPException(409, "Build a BOM before exporting reports.")

    if kind == "bom.csv":
        content = bom_table(b).to_csv(index=False)
        media = "text/csv"
        filename = "robot_bom.csv"
    elif kind == "ledger.csv":
        content = ledger_table(b, state.spec_defs).to_csv(index=False)
        media = "text/csv"
        filename = "evidence_ledger.csv"
    elif kind == "report.md":
        power = analyze_power(b, state.config)
        wiring = generate_wiring_plan(b)
        content = generate_markdown_report(b, req, state.config, state.spec_defs, power, wiring)
        media = "text/markdown"
        filename = "robot_report.md"
    elif kind == "report.html":
        content = generate_html_report(b, req, state.config, state.spec_defs)
        media = "text/html"
        filename = "robot_report.html"
    else:
        raise HTTPException(404, "Unknown export format")

    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
