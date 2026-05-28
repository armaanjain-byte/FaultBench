"""Tests for the static site generator.

The critical test verifies that the generated HTML contains rendered HTML
tags (e.g. <strong>) rather than raw Markdown syntax (e.g. **bold**).
"""
from __future__ import annotations

import os
import sys

import pytest

# Ensure the task root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tasks.task_004_markdown_site.parser import parse_markdown, extract_title  # noqa: E402
from tasks.task_004_markdown_site.templates import render_page  # noqa: E402
from tasks.task_004_markdown_site.generator import generate_site  # noqa: E402


# ------------------------------------------------------------------
# Parser tests
# ------------------------------------------------------------------

class TestParser:
    def test_parse_heading(self):
        html = parse_markdown("# Hello World")
        assert "<h1>" in html
        assert "Hello World" in html

    def test_parse_bold(self):
        html = parse_markdown("This is **bold** text")
        assert "<strong>bold</strong>" in html

    def test_parse_list(self):
        md = "- Item A\n- Item B\n"
        html = parse_markdown(md)
        assert "<li>" in html

    def test_extract_title_found(self):
        assert extract_title("# My Page\nSome text") == "My Page"

    def test_extract_title_missing(self):
        assert extract_title("No heading here") == "Untitled"


# ------------------------------------------------------------------
# Template tests — this is where the bug surfaces
# ------------------------------------------------------------------

class TestTemplates:
    def test_render_page_contains_html_not_markdown(self):
        """The rendered page MUST contain HTML tags, not raw Markdown.

        This is the critical test that catches the raw-markdown bug.
        """
        md_source = "# Test Page\n\nThis is **bold** and *italic*."
        html_content = parse_markdown(md_source)
        page_title = extract_title(md_source)

        rendered = render_page(
            markdown_source=md_source,
            html_content=html_content,
            page_title=page_title,
        )

        # The rendered page must contain HTML tags from the parsed markdown
        assert "<strong>bold</strong>" in rendered, (
            "Rendered page contains raw Markdown instead of HTML — "
            "templates.py is passing markdown_source instead of html_content"
        )
        assert "<em>italic</em>" in rendered

    def test_render_page_does_not_contain_raw_markdown_bold(self):
        """Raw Markdown bold syntax (**text**) must NOT appear in output."""
        md_source = "Some **important** text"
        html_content = parse_markdown(md_source)
        page_title = "Test"

        rendered = render_page(
            markdown_source=md_source,
            html_content=html_content,
            page_title=page_title,
        )

        assert "**important**" not in rendered, (
            "Raw Markdown bold syntax found in rendered output"
        )

    def test_render_page_includes_site_title(self):
        rendered = render_page(
            markdown_source="# X",
            html_content="<h1>X</h1>",
            page_title="X",
        )
        assert "My Benchmark Site" in rendered


# ------------------------------------------------------------------
# Integration test
# ------------------------------------------------------------------

class TestGeneratorIntegration:
    def test_generate_site_creates_html_files(self, tmp_path, monkeypatch):
        """generate_site should create .html files in the output directory."""
        task_dir = os.path.join(os.path.dirname(__file__), "..")
        monkeypatch.chdir(task_dir)

        # Use a temp output directory so we don't pollute the task dir
        import yaml
        config_path = os.path.join(task_dir, "config.yaml")
        with open(config_path) as fh:
            config = yaml.safe_load(fh)
        config["output_dir"] = str(tmp_path / "_site")

        tmp_config = tmp_path / "config.yaml"
        with open(tmp_config, "w") as fh:
            yaml.dump(config, fh)

        files = generate_site(str(tmp_config))
        assert len(files) >= 2  # index.html and about.html

        for f in files:
            content = open(f, "r").read()
            # All output files should contain <main> from the template
            assert "<main>" in content
            # None should contain raw Markdown headings (# Title)
            # The title may appear in <title> or <h1> tags but not as raw MD
            assert "\n# " not in content, (
                f"Raw Markdown heading found in {f}"
            )

    def test_generated_index_has_html_content(self, tmp_path, monkeypatch):
        """The generated index.html must have HTML-rendered content."""
        task_dir = os.path.join(os.path.dirname(__file__), "..")
        monkeypatch.chdir(task_dir)

        import yaml
        config_path = os.path.join(task_dir, "config.yaml")
        with open(config_path) as fh:
            config = yaml.safe_load(fh)
        config["output_dir"] = str(tmp_path / "_site")

        tmp_config = tmp_path / "config.yaml"
        with open(tmp_config, "w") as fh:
            yaml.dump(config, fh)

        generate_site(str(tmp_config))

        index_html = (tmp_path / "_site" / "index.html").read_text()
        # The index page has **home page** which should become <strong>
        assert "<strong>" in index_html, (
            "index.html does not contain <strong> — raw Markdown was passed "
            "to the template instead of rendered HTML"
        )
