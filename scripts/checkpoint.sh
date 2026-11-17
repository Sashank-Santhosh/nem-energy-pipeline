#!/usr/bin/env bash
# Save the database mid-backfill so a timeout never loses hours of work.
# Needs old.json (row counts at the last save); refuses to upload if any raw table shrank.
set -euo pipefail
uv run python -m ingest.cli counts --db nem.duckdb > new.json
uv run python -m ingest.cli guard --old old.json --new new.json
bash scripts/release_db.sh upload nem.duckdb
cp new.json old.json
