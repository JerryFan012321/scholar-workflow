"""Small shared process environment for local native-tool launch helpers."""
from __future__ import annotations

import os

_BASE_CHILD_ENV_KEYS = ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL")
_CMUX_CHILD_ENV_KEYS = ("CMUX_WORKSPACE_ID", "CMUX_SOCKET_PATH")


def minimal_child_environment(*, include_cmux: bool = False) -> dict[str, str]:
    """Return the small environment required by local launch helpers."""
    keys = _BASE_CHILD_ENV_KEYS + (_CMUX_CHILD_ENV_KEYS if include_cmux else ())
    return {
        key: value
        for key in keys
        if (value := os.environ.get(key)) is not None
    }


__all__ = ["minimal_child_environment"]
