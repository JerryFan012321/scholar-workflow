# Security Policy (shared)

Canonical safety boundaries. Applies to all skills, agents, and services.

## Claude permission boundary

| Action | Rule |
|---|---|
| Read local index / state / Zotero Local API | Allowed |
| User-authorized web search | Allowed |
| Download PDF from arXiv | Show plan, get approval first |
| Write Zotero / move PDF / write Vault / write Notion | Show plan, get approval first |
| Delete, overwrite conflicts, merge items | Never automatic — per-item approval |
| Write `zotero.sqlite` directly | Permanently forbidden |

## Approval gate

- External writes require a valid, approved `plan_id`.
- Any change to plan content invalidates the prior approval.
- On identity conflict, stop that item without affecting other safe items.

## Loopback services

- Zotero Bridge and the local-link service bind to `127.0.0.1` only.
- Tokens go in headers, never in URLs. Write requests require `Idempotency-Key`.
- Services accept opaque IDs / canonical paths only; reject `..` and symlink escapes.

## Logging

Never log tokens, paper full text, or sensitive absolute paths. Log normalized
relative paths and resource IDs only.
