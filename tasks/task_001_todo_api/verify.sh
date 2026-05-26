#!/bin/bash
set -e
# Install dependencies into the current environment before running tests.
# The lifecycle runner sets cwd to work_dir before calling this script.
pip install -q -r requirements.txt
python -m pytest tests/ -v --tb=short
