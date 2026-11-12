# Recommendation service

The installed HTTP service only presents the selected recommendation pool. Producers
and curators continue using the CLI without any browser or running HTTP service.

## Normal use

```sh
scholar-research recommendations start
scholar-research recommendations open
scholar-research recommendations open --no-browser
scholar-research recommendations status
scholar-research recommendations restart
scholar-research recommendations stop
```

The personal pool defaults to **http://127.0.0.1:61201/**. Save this ordinary URL
as a bookmark or open it simultaneously in multiple browsers/cmux surfaces on this
Mac. No token or extra URL component is needed. Closing browsers or terminals has
no effect on the service. `start` and `open` reuse a healthy current installation.

On macOS, these commands register the personal service as a user LaunchAgent, using
the installed Python executable. It starts at user login and launchd restarts it on
abnormal exit. It does not run before login, while logged out, or while the Mac is
asleep/offline. This is a loopback-only service, not phone/LAN/Internet access.
No agent/model execution is scheduled by this registration.

`stop` stops only the identified owned service and removes its LaunchAgent, so it
stays stopped across login until `start` or `open` is explicitly run again. It does
not delete candidates, feedback, context, endpoint choice or other research data.
`restart` reuses the saved address. On non-macOS platforms the service is detached
but has no login/recovery supervisor; `status` states this explicitly.

## Port conflicts and test isolation

If the address is occupied by another program, startup fails with a clear diagnostic.
It never kills that program or silently changes URL. The existing service is left
running when an explicitly requested different port is already occupied.
To deliberately choose and save another port:

```sh
scholar-research recommendations start --port 61203
```

Subsequent start/open/restart use that saved choice. The private `endpoint.json`
contains only the selected port; `runtime.json` contains current process/session
identity. They live in the selected pool beside its database and must not be copied
into public repositories. Do not edit these records to claim that a service is live.

Tests must use `--profile test` with the explicitly selected isolated state root.
A test pool chooses an unused port once and saves it for restarts; it never uses the
personal default or installs a login service. Multiple test roots remain independent.
No producer command starts or supervises the HTTP service.

## Diagnosis and updates

`status` reports running/stopped/unavailable, executable, package/build, address and
`manager`, `login_start`, `supervised`. These fields describe the actual registration
and launchd job, not a promise based only on a stored plist. Tokens are never printed.
A copied/changed unsafe LaunchAgent or unidentifiable process is refused without
being overwritten or terminated. Repeated crashes or a port collision require the
user/agent to inspect status and the private service log, not to kill unknown PIDs.

Install releases normally, then run `start` to verify and replace only the owned old
service while preserving the saved port and data. The service never requires a source
checkout or code-repo-root setting. Returning to a pre-0.54.2 version requires stopping
0.54.2 first (to remove its supervisor); the older version uses dynamic URLs again.
