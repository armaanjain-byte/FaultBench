# Task 004 — Markdown Site Generator

## Overview
A static site generator that reads `.md` files from a content directory, converts them to HTML via the `markdown` library, renders them into a Jinja2 base template, and writes the final `.html` files to an output directory.

## The Bug
`templates.py :: render_page` receives both `markdown_source` (raw Markdown) and `html_content` (rendered HTML) as parameters. However, it passes `markdown_source` to the Jinja template's `content` variable instead of `html_content`. This means the generated HTML pages display raw Markdown syntax rather than properly rendered HTML.

## Expected Behaviour
The `{{ content }}` block in `base.html` should contain rendered HTML (e.g. `<strong>bold</strong>`) — not raw Markdown (`**bold**`).

## Running
```bash
pip install -r requirements.txt
python generator.py
```

## Verification
```bash
bash verify.sh
```
