# Security Policy (shared)

Canonical safety boundaries. Applies to all skills, agents, and services.

## Claude permission boundary

| Action | Rule |
|---|---|
| Read local index / state / Zotero Local API | Allowed |
| User-authorized web search | Allowed |
| Download PDF from arXiv to `paper_inbox` | Show plan, get approval first |
| Write to Zotero programmatically | Forbidden — import is manual |
| Move PDF / write Vault / write Notion | Show plan, get approval first |
| Delete, overwrite conflicts, merge items | Never automatic — per-item approval |
| Write `zotero.sqlite` directly | Permanently forbidden |

## Approval gate

- Downloads and Vault/Notion writes require in-conversation approval of the plan.
- Approval is a dialogue act — there is no persisted plan file or `plan_id`. Any
  change to the resolved input list invalidates the prior approval.
- On identity conflict, stop that item without affecting other safe items.

## Loopback services

- The local-link service binds to `127.0.0.1` only.
- The Zotero Local API is read-only; queries carry no tokens or write payloads.
- Services accept opaque IDs / canonical paths only; reject `..` and symlink escapes.

## Logging

Never log tokens, paper full text, or sensitive absolute paths. Log normalized
relative paths and resource IDs only.
