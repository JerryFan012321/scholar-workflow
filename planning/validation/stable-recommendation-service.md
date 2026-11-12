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

Normal 0.54.2 release/install completed on pipx and both plugin hosts. All six
scoped checks passed: reuse, stable restart, explicit stop without supervision,
health-identified HTTP abnormal-exit recovery, two independent plain URL sessions,
and test restart with its separate saved address and no login job.
Both pools retained identical complete candidate API snapshots before/after.
Browser displayed the fixed personal URL. Local detailed receipts/screenshots are
private; no candidate data or runtime paths are published here.
Actual logout/reboot remains unexecuted. Login startup policy and loaded job were
verified, not represented as an observed reboot/login test.
