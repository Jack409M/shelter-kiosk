#!/usr/bin/env bash
set -euo pipefail

echo "[restore] resetting repo to origin/main"
git fetch origin
git reset --hard origin/main

echo "[restore] creating fresh virtual environment"
python -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

echo "[restore] running full test suite"
pytest -q

echo "[restore] restore verification complete"
