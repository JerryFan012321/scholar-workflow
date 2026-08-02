"""Scholar Inbox API client — zero-dependency wrapper using only stdlib.

Adapted from https://github.com/jiahao-shao1/sjh-skills (MIT License,
Copyright (c) 2026 Jiahao Shao). See ../THIRD_PARTY_LICENSES.
Local edit: import Config via relative import (vendored as a package).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlencode

from .config import Config

API_BASE = "https://api.scholar-inbox.com/api"

RATING_MAP = {"up": 1, "down": -1, "reset": 0}


class APIError(Exception):
    """Non-recoverable API error."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class SessionExpiredError(APIError):
    """Session cookie is missing or expired."""

    def __init__(self, message: str = "Session expired or not set. Run 'si login' first."):
        super().__init__(message, status=401)


class ScholarInboxClient:
    """Thin wrapper around the Scholar Inbox REST API."""

    def __init__(
        self,
        session: str | None = None,
        config: Config | None = None,
        config_dir=None,
    ):
        self._config = config or Config(config_dir=config_dir) if (config or config_dir) else None
        self._session = session

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_session(self) -> str:
        if self._session:
            return self._session
        if self._config:
            s = self._config.load_session()
            if s:
                self._session = s
                return s
        raise SessionExpiredError()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        body: dict | None = None,
        needs_session: bool = True,
    ) -> dict | None:
        if needs_session:
            cookie = self._ensure_session()

        url = f"{API_BASE}{path}"
        if params:
            url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"

        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "ScholarInboxCLI/0.1")
        if needs_session:
            req.add_header("Cookie", f"session={cookie}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                # Auto-renew session from Set-Cookie header
                set_cookie = resp.headers.get("Set-Cookie", "")
                if set_cookie and "session=" in set_cookie:
                    new_val = set_cookie.split("session=")[1].split(";")[0]
                    if new_val and new_val != self._session:
                        self._session = new_val
                        if self._config:
                            self._config.save_session(new_val)

                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise SessionExpiredError() from exc
            raise APIError(f"HTTP {exc.code}: {exc.reason}", status=exc.code) from exc

    # ------------------------------------------------------------------
    # Public API (read-only subset used by recommend-papers)
    # ------------------------------------------------------------------

    def check_session(self) -> dict:
        """Verify the current session is valid."""
        return self._request("GET", "/session_info")

    def get_digest(
        self,
        date: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        """Fetch the paper digest."""
        params = {"date": date, "from": from_date, "to": to_date}
        return self._request("GET", "/", params=params)

    def get_paper(self, paper_id: int) -> dict | None:
        """Fetch details for a single paper from current digest.

        The upstream `/?paper_id=...` endpoint is not stable: it may return a
        full digest page instead of the requested paper. Filter explicitly by
        `paper_id` so callers never get the wrong paper by accident.
        """
        data = self._request("GET", "/", params={"paper_id": paper_id})
        if data and data.get("digest_df"):
            for row in data["digest_df"]:
                if row.get("paper_id") == paper_id:
                    return row
        return None
