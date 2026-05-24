# Task 005 — Inventory CLI

## Overview
A CLI-based inventory management tool built with Click. Supports adding, removing, searching, listing, and updating items. Data is persisted in a JSON file.

## The Bug
`inventory.py :: search_items` uses **exact string equality** (`==`) to compare the query against item names. The specification requires **case-insensitive substring matching** — for example, searching for `'wid'` should match `'Widget A'`, and `'WIDGET'` should match `'widget'`.

## Expected Behaviour
`search_items("wid")` should return all items whose name contains the substring `wid` regardless of case.

## Running
```bash
pip install -r requirements.txt
python cli.py add "Widget A" -p 5.00 -q 10
python cli.py search "wid"
```

## Verification
```bash
bash verify.sh
```
