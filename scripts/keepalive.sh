#!/usr/bin/env bash
# GitHub switches off scheduled workflows in a public repository after 60 days with no
# repository activity. If the last commit is older than 30 days, make one empty commit and
# push it, so the hourly data job keeps running while nobody is working on the project.
set -euo pipefail

MAX_AGE_DAYS="${KEEPALIVE_DAYS:-30}"
age=$(( $(date +%s) - $(git log -1 --format=%ct) ))

if [ "$age" -le $(( MAX_AGE_DAYS * 86400 )) ]; then
  echo "keepalive: last commit is $(( age / 86400 )) days old, nothing to do"
  exit 0
fi

git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit --allow-empty -q -m "chore: keep scheduled jobs alive (no commits for ${MAX_AGE_DAYS}+ days)"
# If the branch moved meanwhile, someone just pushed, so the repository is active anyway.
git push -q origin "HEAD:${GITHUB_REF_NAME:-main}" \
  || echo "keepalive: push skipped (the branch moved, so the repository is active anyway)"
echo "keepalive: made an empty commit after ${MAX_AGE_DAYS}+ quiet days"
