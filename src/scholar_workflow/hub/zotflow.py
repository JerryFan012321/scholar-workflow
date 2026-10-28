"""Compatibility alias for the shared ZotFlow reader and annotation adapter.

The module identity is shared so legacy private helpers and monkeypatches
remain valid without a second implementation.
"""
import sys

from scholar_workflow.adapters import zotflow as _implementation

sys.modules[__name__] = _implementation
