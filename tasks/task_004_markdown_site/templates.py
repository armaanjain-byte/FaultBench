"""HTML template handling via Jinja2.

BUG: render_page passes the raw Markdown source text to the template as
``content`` instead of the HTML-rendered version.  The Jinja template
therefore displays unprocessed Markdown in the browser.
"""
from __future__ import annotations

from jinja2 import Environment, FileSystemLoader
import yaml


def _load_config() -> dict:
    with open("config.yaml", "r") as fh:
        return yaml.safe_load(fh)


def render_page(
    markdown_source: str,
    html_content: str,
    page_title: str,
) -> str:
    """Render a page by injecting content into the Jinja2 base template.

    Parameters
    ----------
    markdown_source:
        The raw Markdown source text (should NOT be used in the template).
    html_content:
        The Markdown already rendered to HTML (SHOULD be used).
    page_title:
        Title extracted from the Markdown heading.

    Returns
    -------
    str
        The fully-rendered HTML page.

    BUG: ``content`` is set to ``markdown_source`` (raw Markdown) instead of
    ``html_content`` (rendered HTML).  Fix by changing the assignment.
    """
    config = _load_config()
    env = Environment(
        loader=FileSystemLoader(config["template_dir"]),
        autoescape=False,  # We trust our own HTML output
    )
    template = env.get_template(config["template_name"])

    # BUG: should be html_content, not markdown_source
    rendered = template.render(
        content=markdown_source,
        title=page_title,
        site_title=config["site_title"],
    )
    return rendered
