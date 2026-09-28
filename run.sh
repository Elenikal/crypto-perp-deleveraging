#!/usr/bin/env bash
# One command, from a fresh clone to results. Downloads ~240 MB of free public
# files on the first run and caches them; re-runs skip what is already there.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "creating .venv"
  python3 -m venv .venv
fi
./.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt

echo "fetching data (free, no account, cached after the first run)"
./.venv/bin/python fetch.py

echo "analysing"
./.venv/bin/python analyze.py
