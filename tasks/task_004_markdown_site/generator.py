"""Static site generator — reads Markdown files and produces HTML pages."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tasks.task_004_markdown_site.parser import parse_markdown, extract_title
from tasks.task_004_markdown_site.templates import render_page


def load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    """Load site-generator configuration."""
    with open(config_path, "r") as fh:
        return yaml.safe_load(fh)


def generate_site(config_path: str = "config.yaml") -> list[str]:
    """Generate the full static site.

    Returns a list of output file paths that were written.
    """
    config = load_config(config_path)
    content_dir = Path(config["content_dir"])
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    written_files: list[str] = []

    for md_file in sorted(content_dir.glob("*.md")):
        markdown_source = md_file.read_text(encoding="utf-8")

        # Parse markdown → HTML
        html_content = parse_markdown(markdown_source)
        page_title = extract_title(markdown_source)

        # Render into template
        full_html = render_page(
            markdown_source=markdown_source,
            html_content=html_content,
            page_title=page_title,
        )

        # Write output
        output_file = output_dir / md_file.with_suffix(".html").name
        output_file.write_text(full_html, encoding="utf-8")
        written_files.append(str(output_file))

    return written_files


if __name__ == "__main__":
    files = generate_site()
    print(f"Generated {len(files)} pages:")
    for f in files:
        print(f"  {f}")
