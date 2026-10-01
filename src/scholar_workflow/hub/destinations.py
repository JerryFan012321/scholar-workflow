"""Runtime-only cmux destinations.

A destination answers only *where a window should appear*.  It is never used
to authorize Vault, project, or task filesystem access.
"""
from __future__ import annotations

import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import field_validator, model_validator

from scholar_workflow.hub.cmux import (
    CmuxControlError,
    WorkspaceRegistry,
)
from scholar_workflow.knowledge.catalog_models import HubModel


class CmuxDestination(HubModel):
    destination_id: str
    cmux_instance_fingerprint: str
    workspace_id: str
    display_name: str
    expires_at: datetime
    is_default: bool = False

    @field_validator("destination_id", "workspace_id", "display_name")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        if not value or value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("destination fields must be clean text")
        return value

    @field_validator("cmux_instance_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("invalid cmux instance fingerprint")
        return value

    @model_validator(mode="after")
    def _future_expiry(self) -> CmuxDestination:
        if self.expires_at.tzinfo is None:
            raise ValueError("destination expiry must be timezone-aware")
        return self


class DestinationRegistry:
    """Process-local destinations keyed by opaque browser handles."""

    def __init__(
        self,
        workspaces: WorkspaceRegistry,
        *,
        now: Callable[[], datetime] | None = None,
        ttl: timedelta = timedelta(hours=8),
    ) -> None:
        if ttl <= timedelta(0) or ttl > timedelta(days=1):
            raise ValueError("destination TTL must be positive and at most one day")
        self.workspaces = workspaces
        self._now = now or (lambda: datetime.now(UTC))
        self._ttl = ttl
        self._destinations: dict[str, CmuxDestination] = {}
        self._instance_defaults: dict[str, str] = {}
        self._lock = threading.RLock()

    def register_default_from_raw(
        self,
        *,
        instance_token: str,
        raw_workspace_id: str,
    ) -> CmuxDestination:
        opaque = self.workspaces.opaque_for_raw(raw_workspace_id)
        listing = self.workspaces.public_workspaces(instance_token=instance_token)
        workspace = next((row for row in listing.workspaces if row.id == opaque), None)
        if workspace is None:
            raise CmuxControlError("Current cmux workspace is no longer live")
        destination = self._register(
            opaque_workspace_id=opaque,
            display_name=workspace.label,
            is_default=True,
        )
        with self._lock:
            previous = self._instance_defaults.get(instance_token)
            if previous and previous in self._destinations:
                prior = self._destinations[previous]
                self._destinations[previous] = prior.model_copy(update={"is_default": False})
            self._instance_defaults[instance_token] = destination.destination_id
        return destination

    def list_for_instance(self, instance_token: str | None) -> list[CmuxDestination]:
        listing = self.workspaces.public_workspaces(instance_token=instance_token)
        if listing.capability_error is not None:
            raise CmuxControlError(listing.capability_error)
        now = self._now()
        with self._lock:
            self._expire(now)
            default_id = self._instance_defaults.get(instance_token or "")
            by_workspace = {
                row.workspace_id: row
                for row in self._destinations.values()
                if row.cmux_instance_fingerprint == self.workspaces.instance_fingerprint()
            }
            result = []
            for workspace in listing.workspaces:
                destination = by_workspace.get(workspace.id)
                if destination is None:
                    destination = self._register(
                        opaque_workspace_id=workspace.id,
                        display_name=workspace.label,
                        is_default=False,
                    )
                is_default = destination.destination_id == default_id
                if destination.is_default != is_default:
                    destination = destination.model_copy(update={"is_default": is_default})
                    self._destinations[destination.destination_id] = destination
                result.append(destination)
            return result

    def resolve(self, destination_id: str) -> str:
        workspace_id, _fingerprint = self.resolve_with_instance(destination_id)
        return workspace_id

    def resolve_with_instance(self, destination_id: str) -> tuple[str, str]:
        """Resolve a live window and return its validated cmux instance identity."""
        now = self._now()
        with self._lock:
            self._expire(now)
            destination = self._destinations.get(destination_id)
        if destination is None:
            raise CmuxControlError("Unknown or expired cmux destination")
        current = self.workspaces.instance_fingerprint()
        if current != destination.cmux_instance_fingerprint:
            raise CmuxControlError("cmux instance changed; choose a destination again")
        # Refresh proves the workspace still exists.  Return the opaque handle;
        # the existing launcher performs the final raw-ID resolution immediately.
        self.workspaces.resolve(destination.workspace_id)
        return destination.workspace_id, destination.cmux_instance_fingerprint

    def _register(
        self,
        *,
        opaque_workspace_id: str,
        display_name: str,
        is_default: bool,
    ) -> CmuxDestination:
        destination = CmuxDestination(
            destination_id=f"dst_{secrets.token_urlsafe(24)}",
            cmux_instance_fingerprint=self.workspaces.instance_fingerprint(),
            workspace_id=opaque_workspace_id,
            display_name=display_name,
            expires_at=self._now() + self._ttl,
            is_default=is_default,
        )
        with self._lock:
            self._destinations[destination.destination_id] = destination
        return destination

    def _expire(self, now: datetime) -> None:
        expired = {
            key for key, value in self._destinations.items() if value.expires_at <= now
        }
        for key in expired:
            del self._destinations[key]
        for instance, destination_id in list(self._instance_defaults.items()):
            if destination_id not in self._destinations:
                del self._instance_defaults[instance]


__all__ = ["CmuxDestination", "DestinationRegistry"]
