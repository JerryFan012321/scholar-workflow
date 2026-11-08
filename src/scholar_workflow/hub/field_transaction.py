"""Compatibility alias for the native knowledge Field transaction implementation."""

import sys

from scholar_workflow.knowledge import field_transaction as _implementation

sys.modules[__name__] = _implementation
