# Research tracking development verification

Date: 2026-10-24. Branch: `codex/hotfix-research-resource-tracking`.
Candidate version: 0.48.0. This is uncommitted development work, not a publication,
normal installation, real-source canary or fresh-dialog one-shot acceptance.

## Scope and prepared inputs

The test plan was written in research-resource-tracking.md and explained in the
conversation before execution. Synthetic isolated configuration/state, RSS/Atom,
HTML and GitHub/HF JSON exercise registration, checks, incremental state and human
output. MockTransport or a synthetic network backend avoids DNS/socket requests.
No formal Vault, Zotero, server, service or subscription was changed.

## Development results

- Initial tool commands without temporary pytest/ruff did not start (missing tools,
  exit 2). Offline cached `uv run --offline --locked --with pytest --with ruff`
  provided the developer runtime without new product dependencies.
- Initial public/local integration and existing related regressions: 111 passed.
  After core refinements, the wider local assets/config/ownership/version subset:
  249 passed. These overlapping counts are not additive.
- Prepared core audit fixtures first exposed 13 failures (duplicate canonical
  channel URLs, diagnostic loss and historical source attribution). Fixed tests
  and the rest of the owned core subset passed. Two later publisher-date-only
  cases first failed, then passed after preventing spurious content-update events.
- Independent review found domain-to-private-address access, Atom xml:base link
  resolution, and non-unicast is_global exceptions. DNS/IP pinning and Atom fixes
  retain original-host TLS and HTTP/HTTPS proxies. The final address fixtures
  first produced 9 failures/2 passes; all 11 passed after all three boundaries
  rejected multicast/reserved/site-local addresses. Independent final replay:
  29 passed, no additional findings in that bounded scope.
- All new tests: **160 passed in 0.39s**. This includes a public local registration
  through the real RSS parser to baseline, revision/new events, transport failure,
  304 recovery, disposition read-back and readable output. It is not installed use.
- The real HTTPX/httpcore with a synthetic backend checks numeric TCP/CONNECT
  targets, original Host and TLS wrap_bio hostname with CERT_REQUIRED/check_hostname
  for direct, HTTP proxy and HTTPS proxy paths. It does not perform a real
  certificate-chain handshake, remote proxy check or production network canary.
- New/changed research modules, adapter, asset renderer, wrapper and tests: Ruff
  passes. cli.py retains its pre-existing unrelated TRY004 in the server JSON
  parser; it was not silently fixed or reported as clean.
- New Skill and modified manage-assets Skill structural validators pass. Routing,
  safety and outcome files validate, but this is not behavioral one-shot proof.
- Offline wheel builds. All **134 Python files** exactly match current source;
  both console entries exist, including `scholar-research`. No wheel was installed.
  Scratch build is disposable under `/private/tmp/scholar-research-build.D8WKL8`.
- Full `tests/unit tests/contract`: **3555 passed, 11 existing warnings in 154.76s**.
  This complete-suite run followed the bounded red/green fixes above and preceded
  the installation-diagnostic follow-up below. It is not installed/live acceptance.

## Installation-diagnostic follow-up

An independent read-only audit confirmed both console declarations but found that
marketplace and package installation are independent, existing README commands
did not pin the same source, and the new console had no version diagnostic. The
plugin wrapper is not a universal fallback for a package isolated by pipx.

Prepared in conversation before execution: isolated absent state, fail on any
network adapter call, invoke version and both help entrypoints; expect exit 0,
actual package version and no created configuration. The version case failed as
expected (unknown option), while the two help cases passed. Added the Click version
option, the shared preflight and matching English/Chinese install/update guidance.
No hook interception, installer, dependency or package version change was needed.

Affected public contracts: **15 passed in 0.15s**. All batch tests after the follow-up:
**163 passed in 2.25s**; changed-code Ruff and diff checks pass. The earlier full
suite remains earlier evidence, not a claim of 3558 current full-suite passes.
Rebuilt offline wheel at
`/private/tmp/scholar-research-build.tEBeWs/scholar_workflow-0.48.0-py3-none-any.whl`:
all 134 Python files match current source, both console declarations and the version
option are present. No wheel/package/plugin was installed. Host PATH resolution,
exact installed build, real network and fresh-dialog use remain unverified.

## Preserved and outstanding

Read-only source preparation on 2026-10-24 identified eight official candidates;
the selected Lil’Log RSS input was directly readable and had usable item metadata.
This did not execute the plugin or register subscriptions. Exact scope and the
unexecuted single-object installed test are in research-resource-tracking-acceptance.md.

No changes to analysis/paper Canvas, Field-tree, project or experiment implementation
or owning Skills; the installed PATH CLI remains 0.47.5. Existing test/Vault data and
the Genie3/L1-cache registration blocker were not repaired or retried.

Before product acceptance: freeze an explicitly authorized source commit, perform
the normal runtime-only hotfix publication/install, then reproduce one controlled
object in `test` from a fresh context. Check real sources, rendering and human
readability separately. No monitoring schedule is created. Model-family dossiers,
selected-resource archive handoff and any explicit scheduling remain the full
direction's unfinished work; G17/G19 remain active and outcome pending.
