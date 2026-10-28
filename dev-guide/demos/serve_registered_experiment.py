"""Serve real registered test units with a visible experiment-only state label."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scholar_workflow.adapters.knowledge_explorer import make_server
from scholar_workflow.knowledge.exploration_environment import ExplorerEnvironment


class LabeledStore:
    def __init__(self, store):
        self.store = store

    def load(self):
        current = self.store.load()
        return {**current, "diagnostics": [
            *current.get("diagnostics", []),
            "test Vault · 隔离登记实验：读取真实论文单元与原文件；正式来源登记未修改。",
            "V-JEPA 2.1 的原文与全文索引已可读；目前为资料笔记，深度分析与 Canvas 尚未完成。"]}

    def save(self, *args, **kwargs):
        self.store.save(*args, **kwargs)
        return self.load()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--test-root", type=Path, required=True)
    args = parser.parse_args()
    context = ExplorerEnvironment("test", args.state, (args.test_root,))
    context.check_root(args.root)
    context.check_registry()
    audit_path = context.state_root / "audit.json"
    if audit_path.is_symlink() or not audit_path.is_file() or audit_path.stat().st_size > 1024 * 1024:
        raise ValueError("An explicit regular experiment audit is required")
    audit = json.loads(audit_path.read_text())
    if audit["mode"] != "experiment-only" or audit["production_written"]:
        raise ValueError("An explicit nonproduction experiment state is required")
    server, token = make_server(args.root, environment=context)
    server.store = LabeledStore(server.store)
    server.previews.store = server.store
    print(f"Experiment: http://127.0.0.1:{server.server_port}/#token={token}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
