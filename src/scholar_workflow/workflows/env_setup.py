"""Scaffold the personal env-records directory.

The plugin owns no private data. It reads the target directory from config
(`env_records_root`) and lays down a uniform skeleton: gitignored real records
(servers.yaml / apis.yaml) plus committed templates (*.example.yaml), a setup/
tree for per-environment rebuild scripts, a README, and a .gitignore that keeps
real records off git while allowing templates and scripts through.

Idempotent: existing files are never overwritten. The real server ledger starts
empty; examples remain separate from actual registered servers.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

GITIGNORE = """\
# Real records stay local — never pushed.
servers.yaml
apis.yaml

# Templates and rebuild scripts are shareable (no secrets inside).
!*.example.yaml
"""

SERVERS_EXAMPLE = """\
# Server ledger format reference, not a real registered server. The CLI creates
# servers.yaml with an empty list. Connection / environment inventory / meta.
servers:
  - alias: gpu-01                 # SSH Host alias
    host: <ip-or-hostname>
    user: <username>
    port: 22
    key: ~/.ssh/id_ed25519        # private key PATH; the key itself never lives here
    jump: null                    # bastion alias, or null for direct connect
    password: null                # legacy field only; never add plaintext credentials
    credential_ref: null          # external store reference, e.g. keychain:servers/gpu-01
    environments:                 # what conda envs live on this host (list, can be many)
      - name: <env-name>
        python: "3.10"
        cuda: "11.8"              # toolkit inside the env
        key_packages: [torch 2.1]
        compat_notes: <version pitfalls>
        setup_script: setup/gpu-01/<env-name>.sh   # pointer to the external rebuild script
    cuda_driver: "12.2"           # host driver's max supported CUDA (distinct from env toolkit)
    proxy:                        # structured; null each field when not needed
      http: null
      https: null
      no_proxy: null
    purpose: <what this host is for>
    added: 2026-08-02
    notes: <other on-host findings>
"""

APIS_EXAMPLE = """\
# API key ledger — one entry per key. Copy to apis.yaml (gitignored) and paste
# real values there; the template keeps placeholders only.
apis:
  - name: notion
    env_var: SCHOLAR_WORKFLOW_NOTION_TOKEN   # env var the consumer reads
    value: <paste-in-apis.yaml>
    owner: "<whose key: you / an org / a shared account>"
    scope: "<what it is for / which project>"
    added: 2026-08-02
"""

README = """\
# env-records

Personal ledger of API keys and SSH servers. **Not** part of any plugin — the
scholar-workflow plugin only *consumes* this directory (its path comes from the
plugin config field `env_records_root`).

## Layout

```
.
├── servers.example.yaml    # template (committed) — how a server entry looks
├── apis.example.yaml       # template (committed) — how an API entry looks
├── servers.yaml            # REAL records (gitignored) — local only
├── apis.yaml               # REAL records (gitignored) — local only
└── setup/                  # env rebuild scripts, setup/<alias>/<env>.sh (committed)
```

## Rules

- **Templates (`*.example.yaml`) are committed; real records (`servers.yaml`,
  `apis.yaml`) are gitignored and never pushed.** The `.gitignore` enforces this.
- `servers.yaml` starts empty. Use the asset-management skill / server ledger CLI
  to register real non-secret connection facts. Templates are format references;
  do not copy the example server into the real ledger.
- Read the ledger before using or asking for server details. Re-registering an
  identical alias is harmless; changing one requires its current ledger revision.
- SSH private keys remain in their external files and credentials in an external
  credential store. The server ledger records paths / credential references, not
  secret values. Legacy secrets remain hidden and are not automatically migrated.
- `setup/<alias>/<env>.sh` scripts hold conda/pip rebuild recipes — shareable
  knowledge, no secrets. They are committed.
"""


@dataclass
class ScaffoldResult:
    root: Path
    created: list[str]
    skipped: list[str]


# Real records are private on creation; existing bytes and modes stay unchanged.
_TEMPLATES = [
    (".gitignore", GITIGNORE),
    ("README.md", README),
    ("servers.example.yaml", SERVERS_EXAMPLE),
    ("apis.example.yaml", APIS_EXAMPLE),
    ("servers.yaml", "servers: []\n"),
    ("apis.yaml", APIS_EXAMPLE),
    ("setup/.gitkeep", ""),
]


def scaffold(root: Path) -> ScaffoldResult:
    """Lay down the env-records skeleton under `root`, idempotently.

    Creates the directory and every skeleton file that does not yet exist.
    Never overwrites an existing file — real records are safe across re-runs.
    """
    root = Path(root).expanduser()
    created: list[str] = []
    skipped: list[str] = []
    for rel, contents in _TEMPLATES:
        dest = root / rel
        if dest.exists():
            skipped.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        mode = 0o600 if rel in {"servers.yaml", "apis.yaml"} else 0o644
        try:
            descriptor = os.open(dest, flags, mode)
        except FileExistsError:
            skipped.append(rel)
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(contents)
        created.append(rel)
    return ScaffoldResult(root=root, created=created, skipped=skipped)
