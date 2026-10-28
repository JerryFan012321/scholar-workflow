"""Compatibility alias for the native knowledge Field migration implementation."""

import sys

from scholar_workflow.knowledge import field_migration as _implementation

sys.modules[__name__] = _implementation
