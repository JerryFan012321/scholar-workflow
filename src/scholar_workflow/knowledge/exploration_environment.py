"""Explicit state and file boundaries for personal and isolated test explorers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from scholar_workflow import __version__
from scholar_workflow.config import DEFAULT_HOME
from scholar_workflow.knowledge.exploration import ExplorationError
from scholar_workflow.knowledge.fields import FieldRegistryError, KnowledgeSourceRegistry


def _safe_path(value: Path | str, *, directory: bool = False) -> Path:
    """Reject links in every existing component before canonicalizing a path."""
    path = Path(value).expanduser().absolute()
    if ".." in path.parts:
        raise ExplorationError("Environment paths cannot contain parent traversal", 7)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ExplorationError("Environment paths cannot traverse a symlink", 7)
        if current.exists() and current != path and not current.is_dir():
            raise ExplorationError("Environment path has a nondirectory parent", 7)
    if directory and not path.is_dir():
        raise ExplorationError("Selected environment folder is unavailable", 7)
    return path.resolve(strict=directory)


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


@dataclass(frozen=True)
class ExplorerEnvironment:
    """A process-selected environment; browser requests cannot change it."""

    mode: str = "personal"
    state_root: Path | None = None
    allowed_roots: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in {"personal", "test"}:
            raise ExplorationError("Unknown explorer environment", 7)
        if self.is_test and (self.state_root is None or not self.allowed_roots):
            raise ExplorationError("Test mode requires an explicit state root and test root", 7)
        state = self.state_root
        if state is None:
            state = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
        state = _safe_path(state)
        roots = tuple(dict.fromkeys(_safe_path(root, directory=True) for root in self.allowed_roots))
        if self.is_test:
            production = DEFAULT_HOME.expanduser().absolute().resolve()
            if _inside(state, production) or _inside(production, state):
                raise ExplorationError("Test state must be separate from production state", 7)
            if any(root == Path(root.anchor) or root == Path.home().resolve() for root in roots):
                raise ExplorationError("Test roots must be explicit bounded folders", 7)
        object.__setattr__(self, "state_root", state)
        object.__setattr__(self, "allowed_roots", roots)

    @property
    def is_test(self) -> bool:
        return self.mode == "test"

    @property
    def registry_path(self) -> Path:
        return self.state_root / "hub" / "sources.json"

    def check_root(self, root: Path | str) -> Path:
        path = _safe_path(root, directory=True)
        if self.is_test:
            allowed = tuple(_safe_path(item, directory=True) for item in self.allowed_roots)
            if not any(_inside(path, item) for item in allowed):
                raise ExplorationError("Selected folder is outside this test environment", 7)
        return path

    def check_registry(self) -> None:
        """Refuse foreign enabled folders before resolving any Source or reader."""
        if not self.is_test:
            return
        _safe_path(self.registry_path)
        try:
            document = KnowledgeSourceRegistry(self.registry_path).load_document()
            for folder in document.folders:
                if folder.enabled:
                    self.check_root(folder.root)
        except FieldRegistryError as error:
            raise ExplorationError("Test registration cannot be read safely", 7) from error

    def public_info(self, root: Path | str) -> dict:
        path = self.check_root(root)
        return {"mode": self.mode, "label": "测试" if self.is_test else "日常",
                "root_name": path.name, "version": __version__,
                "native_integrations": not self.is_test}
