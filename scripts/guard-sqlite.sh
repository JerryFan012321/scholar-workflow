#!/usr/bin/env bash
# Guard against direct writes to zotero.sqlite.
# Receives tool input as JSON on stdin (Claude Code hook protocol).
# Exit 2 to block; exit 0 to allow.

input=$(cat)

if echo "$input" | grep -qE 'zotero\.sqlite'; then
  echo "BLOCKED: Direct write to zotero.sqlite is permanently forbidden. Use ZoteroWriteAdapter."
  exit 2
fi

exit 0
