"""Detached process entry point for the managed Scholar Workflow Hub."""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path

from scholar_workflow import __version__
from scholar_workflow.config import Config, ConfigNotFound, load_config
from scholar_workflow.hub.compatibility import compatibility_vault_root
from scholar_workflow.hub.lifecycle import (
    DISCOVERY_SCHEMA_VERSION,
    HUB_PROTOCOL_VERSION,
    SERVICE_NAME,
    HubDiscoveryRecord,
    installed_build_hash,
    load_discovery,
    remove_discovery_if_owned,
    utc_now,
    write_discovery,
)
from scholar_workflow.hub.server import start_hub_server


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--generation", required=True)
    parser.add_argument("--discovery", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    options = _arguments(argv)
    discovery = options.discovery.expanduser().resolve()
    log_path = options.log.expanduser().resolve()
    try:
        cfg = load_config()
    except ConfigNotFound:
        cfg = Config()
    vault_root = compatibility_vault_root(cfg.research_vault_root)
    server = start_hub_server(
        port=0,
        storage_root=cfg.link_service.storage_root,
        vault_root=vault_root,
        owner_mode="headless",
        require_workspace_binding=False,
        service_generation=options.generation,
        log_path=log_path,
    )
    record = HubDiscoveryRecord(
        schema_version=DISCOVERY_SCHEMA_VERSION,
        service_name=SERVICE_NAME,
        pid=os.getpid(),
        port=server.server_address[1],
        executable=str(Path(sys.executable).resolve()),
        package_version=__version__,
        build_hash=installed_build_hash(),
        protocol_version=HUB_PROTOCOL_VERSION,
        service_generation=options.generation,
        started_at=utc_now(),
        log_path=str(log_path),
    )
    # Never replace another generation's live discovery record from the child.
    current = load_discovery(discovery)
    if current is not None and (
        current.pid != record.pid
        or current.service_generation != record.service_generation
    ):
        server.shutdown()
        server.server_close()
        raise RuntimeError("another Hub discovery record appeared during startup")
    write_discovery(record, discovery)

    stopping = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        stopping.wait()
    finally:
        server.shutdown()
        server.server_close()
        remove_discovery_if_owned(record, discovery)
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
