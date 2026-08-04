#!/usr/bin/env bash
# Guard against direct writes to zotero.sqlite.
# Receives tool input as JSON on stdin (Claude Code hook protocol).
# Exit 2 to block; exit 0 to allow.

input=$(cat)

if echo "$input" | grep -qE 'zotero\.sqlite'; then
  echo "BLOCKED: naming zotero.sqlite in a shell command is forbidden. All Zotero writes go"
  echo "through zotero-mcp's controlled tools; annotation export reads the DB only via"
  echo "bin/zotero-annotations.py (mode=ro&immutable=1), which never puts the path on the"
  echo "command line. If you hit this, you are on the wrong path — use zotero-mcp."
  exit 2
fi

exit 0
