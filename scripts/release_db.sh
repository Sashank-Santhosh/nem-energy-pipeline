#!/usr/bin/env bash
# Download or upload nem.duckdb as the "data-latest" GitHub Release asset.
# Usage: scripts/release_db.sh download|upload [path]
set -euo pipefail
DB="${2:-nem.duckdb}"
case "${1:-}" in
  download) gh release download data-latest --pattern nem.duckdb --output "$DB" --clobber ;;
  upload)   gh release upload data-latest "$DB#nem.duckdb" --clobber ;;
  *) echo "usage: $0 download|upload [path]" >&2; exit 2 ;;
esac
