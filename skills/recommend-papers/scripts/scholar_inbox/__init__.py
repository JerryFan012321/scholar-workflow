"""Vendored Scholar Inbox client.

Adapted from https://github.com/jiahao-shao1/sjh-skills (MIT License,
Copyright (c) 2026 Jiahao Shao). See ../THIRD_PARTY_LICENSES.
Only api.py, auth.py, config.py were vendored (not upstream cli.py).
"""
from __future__ import annotations

from .api import APIError, ScholarInboxClient, SessionExpiredError
from .config import Config

__all__ = ["APIError", "ScholarInboxClient", "SessionExpiredError", "Config"]
