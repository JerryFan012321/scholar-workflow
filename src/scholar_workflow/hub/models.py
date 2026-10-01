"""Compatibility alias for knowledge-owned catalog models.

Alias the module, not just public names, so legacy private helpers and
monkeypatches continue to address the one canonical implementation.
"""
import sys

from scholar_workflow.knowledge import catalog_models as _implementation

sys.modules[__name__] = _implementation
