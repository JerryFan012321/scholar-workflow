# Stable recommendation service validation

## Scope

0.54.2, isolated hotfix; lifecycle and runtime instructions only. No candidate,
Zotero, knowledge unit, source acquisition or external agent execution changes.

## Synthetic input and expected behavior

- Personal default 61201; explicit saved override and private endpoint persistence.
- Test root retains its independently allocated port across stop/start/restart.
- Current service reuse, unknown-process refusal, requested occupied-port refusal
  before touching the running owned service, private/symlink-safe metadata.
- Synthetic launchd calls: login and unsuccessful-exit policy, idempotent reuse,
  explicit stop removes registration, foreign plist/job refusal, bootstrap failure,
  no tokens in plist, test profile never invokes launchd.
- Real loopback CLI contract uses a synthetic temporary pool, preserves its single
  candidate and URL across repeated starts and restarts.

## Results

45 targeted lifecycle/HTTP/CLI/manifest tests passed (4.75 s).
Recommendation regression: 504 passed, 21 initially failed because the older metrics
DOM simulator lacked document.addEventListener used by the 0.54.1 tag picker.
Only that simulator was extended; all 21 then passed (0.56 s). No product UI change.
Ruff on new lifecycle/background/test code and git diff --check passed.
Machine-local JUnit receipts retain original and rerun results.

## Installed acceptance

Pending normal release/install. Check package/build identity, current manager and
fixed URL, reuse, restart, abnormal-exit recovery, plain sessions in two windows,
explicit stop and restart, test separation and candidate snapshot conservation.
Only verified owned HTTP service processes may be interrupted; no agent is launched.
Actual logout/reboot is not performed automatically or claimed as observed.
