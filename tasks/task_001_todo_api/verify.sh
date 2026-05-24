#!/bin/bash
set -e
cd "$(dirname "$0")"
python -m pytest tests/ -v --tb=short
