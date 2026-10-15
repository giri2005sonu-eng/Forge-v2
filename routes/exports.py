"""Compatibility shim for the older report export route layout."""

from fastapi import HTTPException

from core.export import generate_html_report, generate_markdown_report


def export_report(kind: str, build, req, config, spec_defs, *, include_power=True, include_wiring=True):
    if kind == "report.md":
        return generate_markdown_report(
            build, req, config, spec_defs,
            include_power=include_power, include_wiring=include_wiring,
        )
    if kind == "report.html":
        return generate_html_report(
            build, req, config, spec_defs,
            include_power=include_power, include_wiring=include_wiring,
        )
    raise HTTPException(404, "Unknown export format")
