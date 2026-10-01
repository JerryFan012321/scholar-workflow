"""Compatibility alias for the knowledge-owned Obsidian identity contract."""
import sys

from scholar_workflow.knowledge import obsidian_contract as _implementation

sys.modules[__name__] = _implementation
