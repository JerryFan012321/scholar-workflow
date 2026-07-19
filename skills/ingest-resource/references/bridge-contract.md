# Zotero Bridge Contract (client side)

All Zotero writes go through `ZoteroWriteAdapter`, which calls a self-hosted Bridge
over loopback HTTP. This is the only write path.

## Preconditions

- Call `GET /health` first. If it fails, **stop** — never fall back to the Local
  API or any other bypass (fail-closed).
- Every write request carries an `Idempotency-Key` header.
- The auth token goes in the `X-Scholar-Token` header, never in the URL.

## Endpoint whitelist

- `GET  /health`
- `GET  /collections`
- `GET  /items/{itemKey}`
- `POST /papers/upsert`
- `POST /attachments/link`
- `POST /items/update-metadata`

## Idempotency

Use a deterministic key per action, e.g. `{plan_id}:{resource_id}:zotero`. Re-running
an approved plan must not create duplicate items or attachments.

## Boundaries

Never write `zotero.sqlite` directly, ask the Bridge to run arbitrary code, or send
attachment paths outside `papers_root`. The full permission boundary is in the
shared `references/security-policy.md`; server-side enforcement (bind, path
validation, size limits) is in `integrations/zotero-bridge/manifest.json`.
