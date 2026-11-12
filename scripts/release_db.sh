#!/usr/bin/env bash
# Download or upload nem.duckdb on the "data-latest" GitHub Release, never losing the history:
#   upload   = upload as nem-next.duckdb, then rename current -> nem-prev.duckdb and
#              next -> nem.duckdb (renames are instant; the old copy is only deleted one cycle later)
#   download = nem.duckdb, falling back to nem-prev.duckdb
# Usage: bash scripts/release_db.sh download|upload [path]
set -euo pipefail
DB="${2:-nem.duckdb}"
TAG=data-latest
REPO="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"

asset_id() { gh api "repos/$REPO/releases/tags/$TAG" -q ".assets[] | select(.name == \"$1\") | .id"; }
delete_asset() { [ -n "$1" ] && gh api -X DELETE "repos/$REPO/releases/assets/$1" >/dev/null || true; }
rename_asset() { gh api -X PATCH "repos/$REPO/releases/assets/$1" -f name="$2" >/dev/null; }

case "${1:-}" in
  download)
    gh release download "$TAG" --pattern nem.duckdb --output "$DB" --clobber \
      || gh release download "$TAG" --pattern nem-prev.duckdb --output "$DB" --clobber
    ;;
  upload)
    tmpdir=$(mktemp -d)
    cp "$DB" "$tmpdir/nem-next.duckdb"
    delete_asset "$(asset_id nem-next.duckdb)"          # leftover from a failed earlier upload
    gh release upload "$TAG" "$tmpdir/nem-next.duckdb"  # current nem.duckdb is untouched until this succeeds
    delete_asset "$(asset_id nem-prev.duckdb)"
    cur=$(asset_id nem.duckdb)
    [ -n "$cur" ] && rename_asset "$cur" nem-prev.duckdb
    rename_asset "$(asset_id nem-next.duckdb)" nem.duckdb
    rm -rf "$tmpdir"
    ;;
  *) echo "usage: $0 download|upload [path]" >&2; exit 2 ;;
esac
