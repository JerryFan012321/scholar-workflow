"""Compatibility alias for knowledge Source and Field management.

The module identity is shared so legacy private helpers and monkeypatches
remain valid without a second registry or implementation.
"""
import sys

from scholar_workflow.knowledge import fields as _implementation

sys.modules[__name__] = _implementation
