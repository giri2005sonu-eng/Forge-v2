"""Compatibility wrapper for the report generation API.

This module preserves the older project import path while delegating to the
current implementation in core.export.
"""

from ..export import generate_html_report, generate_markdown_report

__all__ = ["generate_markdown_report", "generate_html_report"]
