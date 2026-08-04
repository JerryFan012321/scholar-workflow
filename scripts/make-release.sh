#!/usr/bin/env bash
# Build the orphan `release` branch from the current dev branch.
#
# The release branch is runtime-only: it contains exactly what a user needs to install
# and run the plugin, and NONE of the development layer (planning/, dev-guide/, tests/,
# evals/, AGENT.md, CLAUDE.md, this script). It has its own independent history; each
# release commit records the source dev SHA it was built from.
#
# Idempotent + re-runnable. Run from a clean working tree on the dev branch:
#   scripts/make-release.sh
# Then review the `release` branch, and push it explicitly when satisfied.
set -euo pipefail

DEV_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
SRC_SHA="$(git rev-parse --short HEAD)"
RELEASE_BRANCH="release"

# Runtime manifest — exactly what ships. Keep in sync with README's release boundary.
RUNTIME_PATHS=(
  ".claude-plugin"
  "agents"
  "bin"
  "contracts"
  "hooks"
  "references"
  "skills"
  "src"
  "scripts/guard-sqlite.sh"
  ".gitignore"
  "CHANGELOG.md"
  "README.md"
  "README.zh-CN.md"
  "pyproject.toml"
)

# Require a pristine tree: tracked changes AND untracked files both block the build.
# `git checkout` carries untracked files across branches, so a stray dev file (review
# note, scratch script, an untracked file inside a runtime dir) would otherwise ride
# into the runtime-only release branch. --porcelain already excludes .gitignored paths.
DIRTY="$(git status --porcelain --untracked-files=all)"
if [ -n "$DIRTY" ]; then
  echo "error: working tree not clean — commit, stash, or remove these first:" >&2
  echo "$DIRTY" >&2
  exit 1
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# Extract the runtime files from the dev commit into a staging dir (archive respects
# .gitignore-tracked state: only committed files are included).
git archive "$DEV_BRANCH" -- "${RUNTIME_PATHS[@]}" | tar -x -C "$WORKDIR"

# Switch to (or create) the orphan release branch.
if git show-ref --verify --quiet "refs/heads/$RELEASE_BRANCH"; then
  git checkout "$RELEASE_BRANCH"
else
  git checkout --orphan "$RELEASE_BRANCH"
fi

# Clear the working tree of tracked files, then lay down the runtime snapshot.
git rm -rfq --ignore-unmatch . >/dev/null 2>&1 || true
cp -R "$WORKDIR"/. .

# Stage only the runtime manifest (the `git rm` above already staged deletions of
# everything else). Never `git add -A` — that would sweep in any untracked leftover.
git add -A -- "${RUNTIME_PATHS[@]}"
if git diff --cached --quiet; then
  echo "release: no changes vs current $RELEASE_BRANCH (already up to date @ $SRC_SHA)"
else
  git commit -q -m "release: sync runtime from $DEV_BRANCH@$SRC_SHA"
  echo "release: committed runtime snapshot from $DEV_BRANCH@$SRC_SHA"
fi

git checkout "$DEV_BRANCH"
echo "done. Review with: git checkout $RELEASE_BRANCH && git status"
