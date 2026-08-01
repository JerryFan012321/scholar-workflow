"""Scaffold the personal env-records directory.

The plugin owns no private data. It reads the target directory from config
(`env_records_root`) and lays down a uniform skeleton: gitignored real records
(servers.yaml / apis.yaml) plus committed templates (*.example.yaml), a setup/
tree for per-environment rebuild scripts, a README, and a .gitignore that keeps
real records off git while allowing templates and scripts through.

Idempotent: existing files are never overwritten. Real record files are seeded
once from their templates and then left alone, so re-running is safe.
"""
from __future__ import annotations
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
# Server ledger — one entry per host. Copy to servers.yaml (gitignored) and fill
# real values. Three blocks per host: connection / environment inventory / meta.
servers:
  - alias: gpu-01                 # SSH Host alias
    host: <ip-or-hostname>
    user: <username>
    port: 22
    key: ~/.ssh/id_ed25519        # private key PATH; the key itself never lives here
    jump: null                    # bastion alias, or null for direct connect
    password: null                # static password if used, else null (local-only, gitignored)
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
- Fill real values by copying a template: `cp servers.example.yaml servers.yaml`,
  then edit. On a new machine, `git clone` restores templates + scripts; re-copy
  and fill the real values locally.
- **record-on-consent (servers):** before a new server is added to the ledger,
  confirm it is worth tracking. Most SSH hosts are throwaway — do not auto-capture.
- SSH private keys and static passwords live only in the gitignored real files
  (or in `~/.ssh/`); they are never committed.
- `setup/<alias>/<env>.sh` scripts hold conda/pip rebuild recipes — shareable
  knowledge, no secrets. They are committed.
"""


@dataclass
class ScaffoldResult:
    root: Path
    created: list[str]
    skipped: list[str]


# (relative path, contents, is_template)
# Real record files are seeded from their template contents but only when absent.
_TEMPLATES = [
    (".gitignore", GITIGNORE),
    ("README.md", README),
    ("servers.example.yaml", SERVERS_EXAMPLE),
    ("apis.example.yaml", APIS_EXAMPLE),
    ("servers.yaml", SERVERS_EXAMPLE),
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
        dest.write_text(contents, encoding="utf-8")
        created.append(rel)
    return ScaffoldResult(root=root, created=created, skipped=skipped)
