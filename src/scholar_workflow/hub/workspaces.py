"""Workspace profiles, leases, and explicit Hub-view bindings."""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from scholar_workflow.hub.models import HubModel

_CLEAN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")


class WorkspaceProfile(HubModel):
    profile_id: str
    role: Literal["hub", "runtime", "notion", "codex"]
    project_id: str | None = None
    aliases: list[str] = Field(default_factory=list)

    @field_validator("profile_id", "project_id")
    @classmethod
    def _clean_optional_id(cls, value: str | None) -> str | None:
        if value is not None and not _CLEAN_ID.fullmatch(value):
            raise ValueError("workspace profile identifiers must be portable")
        return value

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate workspace alias")
        if any(not _CLEAN_ID.fullmatch(value) for value in values):
            raise ValueError("invalid workspace alias")
        return values

    @model_validator(mode="after")
    def _codex_project(self) -> Self:
        if self.role == "codex" and self.project_id is None:
            raise ValueError("codex workspace profiles require project_id")
        if self.role != "codex" and self.project_id is not None:
            raise ValueError("only codex workspace profiles accept project_id")
        return self


class WorkspaceLease(HubModel):
    lease_id: str
    profile_id: str
    opaque_workspace_id: str
    cmux_instance_fingerprint: str
    service_generation: str
    lease_generation: int = Field(ge=1)
    issued_at: datetime
    expires_at: datetime

    @field_validator("cmux_instance_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        if not _FINGERPRINT.fullmatch(value):
            raise ValueError("invalid cmux instance fingerprint")
        return value

    @model_validator(mode="after")
    def _time_order(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("workspace lease must expire after issuance")
        return self


class HubViewBinding(HubModel):
    binding_id: str
    instance_token_hash: str
    primary_lease_id: str
    service_generation: str
    bound_at: datetime


class WorkspaceBindingRegistry:
    """Process-local binding state; aliases and workspace names are never authority."""

    def __init__(
        self,
        *,
        service_generation: str,
        profiles: list[WorkspaceProfile],
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not _CLEAN_ID.fullmatch(service_generation):
            raise ValueError("service_generation must be a portable identifier")
        self.service_generation = service_generation
        self._profiles = {row.profile_id: row for row in profiles}
        if len(self._profiles) != len(profiles):
            raise ValueError("duplicate workspace profile_id")
        self._now = now or (lambda: datetime.now(UTC))
        self._nonces: dict[str, tuple[str, datetime]] = {}
        self._leases: dict[str, WorkspaceLease] = {}
        self._bindings: dict[str, HubViewBinding] = {}
        self._lease_generation = 0
        self._lock = threading.RLock()

    def issue_nonce(
        self,
        instance_token: str,
        *,
        ttl: timedelta = timedelta(minutes=2),
    ) -> str:
        self._validate_instance(instance_token)
        if ttl <= timedelta(0) or ttl > timedelta(minutes=10):
            raise ValueError("nonce ttl must be between zero and ten minutes")
        nonce = secrets.token_urlsafe(32)
        digest = _secret_hash(nonce)
        with self._lock:
            self._nonces[instance_token] = (digest, self._now() + ttl)
        return nonce

    def bind(
        self,
        *,
        instance_token: str,
        nonce: str,
        profile_id: str,
        opaque_workspace_id: str,
        cmux_instance_fingerprint: str,
        ttl: timedelta = timedelta(minutes=30),
    ) -> WorkspaceLease:
        self._validate_instance(instance_token)
        if profile_id not in self._profiles:
            raise ValueError("unknown workspace profile")
        if not opaque_workspace_id or len(opaque_workspace_id) > 256:
            raise ValueError("invalid opaque workspace id")
        if not _FINGERPRINT.fullmatch(cmux_instance_fingerprint):
            raise ValueError("invalid cmux instance fingerprint")
        if ttl <= timedelta(0) or ttl > timedelta(hours=8):
            raise ValueError("workspace lease ttl is out of range")
        now = self._now()
        with self._lock:
            stored = self._nonces.pop(instance_token, None)
            if (
                stored is None
                or stored[1] <= now
                or not secrets.compare_digest(stored[0], _secret_hash(nonce))
            ):
                raise ValueError("nonce is unknown, expired, or already used")
            existing = self._binding_lease(instance_token, now=now)
            if (
                existing is not None
                and existing.cmux_instance_fingerprint != cmux_instance_fingerprint
            ):
                raise ValueError("cmux instance mismatch")
            self._lease_generation += 1
            lease = WorkspaceLease(
                lease_id="lease_" + secrets.token_urlsafe(18),
                profile_id=profile_id,
                opaque_workspace_id=opaque_workspace_id,
                cmux_instance_fingerprint=cmux_instance_fingerprint,
                service_generation=self.service_generation,
                lease_generation=self._lease_generation,
                issued_at=now,
                expires_at=now + ttl,
            )
            binding = HubViewBinding(
                binding_id="binding_" + secrets.token_urlsafe(18),
                instance_token_hash=_secret_hash(instance_token),
                primary_lease_id=lease.lease_id,
                service_generation=self.service_generation,
                bound_at=now,
            )
            self._leases[lease.lease_id] = lease
            self._bindings[instance_token] = binding
            return lease

    def is_bound(self, instance_token: str | None) -> bool:
        if instance_token is None:
            return False
        try:
            self.require_binding(instance_token)
        except ValueError:
            return False
        return True

    def require_binding(
        self,
        instance_token: str,
        *,
        cmux_instance_fingerprint: str | None = None,
    ) -> WorkspaceLease:
        self._validate_instance(instance_token)
        with self._lock:
            lease = self._binding_lease(instance_token, now=self._now())
            if lease is None:
                raise ValueError("Hub view is unbound")
            if lease.service_generation != self.service_generation:
                raise ValueError("service generation mismatch")
            if (
                cmux_instance_fingerprint is not None
                and lease.cmux_instance_fingerprint != cmux_instance_fingerprint
            ):
                raise ValueError("cmux instance mismatch")
            return lease

    def unbind(self, instance_token: str) -> None:
        with self._lock:
            binding = self._bindings.pop(instance_token, None)
            if binding is not None:
                self._leases.pop(binding.primary_lease_id, None)
            self._nonces.pop(instance_token, None)

    def _binding_lease(self, instance_token: str, *, now: datetime) -> WorkspaceLease | None:
        binding = self._bindings.get(instance_token)
        if binding is None:
            return None
        lease = self._leases.get(binding.primary_lease_id)
        if lease is None or lease.expires_at <= now:
            self._bindings.pop(instance_token, None)
            if lease is not None:
                self._leases.pop(lease.lease_id, None)
            return None
        return lease

    @staticmethod
    def _validate_instance(instance_token: str) -> None:
        if (
            not isinstance(instance_token, str)
            or not 8 <= len(instance_token) <= 256
            or instance_token != instance_token.strip()
            or any(ord(char) < 33 or ord(char) > 126 for char in instance_token)
        ):
            raise ValueError("invalid Hub instance token")


class WorkspaceBindingCoordinator:
    """Bind browser-visible opaque handles using only server-resolved cmux identity."""

    def __init__(
        self,
        registry: WorkspaceBindingRegistry,
        *,
        resolve_workspace: Callable[[str], str],
        instance_fingerprint: Callable[[], str],
    ) -> None:
        self.registry = registry
        self._resolve_workspace = resolve_workspace
        self._instance_fingerprint = instance_fingerprint

    def issue_nonce(self, instance_token: str) -> str:
        return self.registry.issue_nonce(instance_token)

    def bind(
        self,
        *,
        instance_token: str,
        nonce: str,
        profile_id: str,
        opaque_workspace_id: str,
    ) -> WorkspaceLease:
        # Resolution proves that the opaque handle is live in this process.  The
        # raw cmux ID is deliberately discarded and never enters the lease/API.
        before = self.current_instance_fingerprint()
        self._resolve_workspace(opaque_workspace_id)
        after = self.current_instance_fingerprint()
        if before != after:
            raise ValueError("cmux instance changed while binding the workspace")
        return self.registry.bind(
            instance_token=instance_token,
            nonce=nonce,
            profile_id=profile_id,
            opaque_workspace_id=opaque_workspace_id,
            cmux_instance_fingerprint=after,
        )

    def current_instance_fingerprint(self) -> str:
        """Return the current server-owned cmux identity, never a client value."""
        fingerprint = self._instance_fingerprint()
        if not _FINGERPRINT.fullmatch(fingerprint):
            raise ValueError("invalid cmux instance fingerprint")
        return fingerprint

    def require_current_binding(self, instance_token: str) -> WorkspaceLease:
        """Revalidate a lease against live cmux state before a controlled action."""
        lease = self.registry.require_binding(instance_token)
        try:
            before = self.current_instance_fingerprint()
            self.registry.require_binding(
                instance_token,
                cmux_instance_fingerprint=before,
            )
            # This callback must perform a live provider lookup.  Its raw result
            # is deliberately discarded so it can never cross the HTTP boundary.
            self._resolve_workspace(lease.opaque_workspace_id)
            after = self.current_instance_fingerprint()
            if before != after:
                raise ValueError("cmux instance changed during workspace validation")
            current = self.registry.require_binding(
                instance_token,
                cmux_instance_fingerprint=after,
            )
            if current.lease_generation != lease.lease_generation:
                raise ValueError("workspace lease changed during validation")
        except Exception:
            self.registry.unbind(instance_token)
            raise
        return lease


def _secret_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "HubViewBinding",
    "WorkspaceBindingCoordinator",
    "WorkspaceBindingRegistry",
    "WorkspaceLease",
    "WorkspaceProfile",
]
