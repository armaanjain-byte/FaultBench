"""Markdown parsing utilities."""
from __future__ import annotations

import markdown


def parse_markdown(source: str) -> str:
    """Convert a Markdown string to HTML.

    Uses the ``markdown`` library with fenced-code-blocks and tables
    extensions enabled.
    """
    extensions = ["fenced_code", "tables"]
    html = markdown.markdown(source, extensions=extensions)
    return html


def extract_title(source: str) -> str:
    """Extract the first ``# heading`` from Markdown source.

    Returns ``"Untitled"`` if no heading is found.
    """
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return "Untitled"
