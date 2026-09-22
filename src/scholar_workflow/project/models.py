"""Strict runtime models matching the public Project System v2 contracts."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256 = r"^[0-9a-f]{64}$"
COMMIT = r"^[0-9a-f]{40}$"
RUN_ID = r"^[0-9]{8}-[0-9]{4}-[a-z0-9][a-z0-9-]{0,47}$"
SLUG = r"^[a-z0-9][a-z0-9-]{0,63}$"


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(
        part in ("", ".", "..") for part in path.parts
    ):
        raise ValueError("path must be safe and relative")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileSnapshot(StrictModel):
    path: str
    sha256: str = Field(pattern=SHA256)

    _validate_path = field_validator("path")(_relative_path)


class SourceRecord(StrictModel):
    commit: str = Field(pattern=COMMIT)


class DatasetRecord(StrictModel):
    dataset_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    split: str = Field(min_length=1)
    manifest: FileSnapshot


class RunRecord(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=RUN_ID)
    created_at: datetime
    record_state: Literal["draft", "frozen", "incomplete_legacy"]
    source: SourceRecord
    entrypoint: FileSnapshot
    config: FileSnapshot
    dataset: DatasetRecord
    seed: int
    environment: FileSnapshot
    recipe_hash: str = Field(pattern=SHA256)


class TargetExecutor(StrictModel):
    kind: Literal["shell", "slurm"]


class TargetProfile(StrictModel):
    schema_version: Literal[1] = 1
    target_id: str = Field(pattern=SLUG)
    kind: Literal["local", "ssh"]
    server_alias: str | None
    project_root: str = Field(min_length=1)
    output_root: str = Field(min_length=1)
    executor: TargetExecutor
    environment_bindings: dict[str, str]

    @model_validator(mode="after")
    def server_alias_matches_kind(self) -> TargetProfile:
        if self.kind == "local" and self.server_alias is not None:
            raise ValueError("local targets require server_alias: null")
        if self.kind == "ssh" and not self.server_alias:
            raise ValueError("ssh targets require a non-empty server_alias")
        if any(not key or not value for key, value in self.environment_bindings.items()):
            raise ValueError("environment bindings require non-empty names and values")
        return self


class ActualExecution(StrictModel):
    working_directory: str | None = None
    output_location: str | None = None
    log_location: str | None = None
    hostname: str | None = None
    os: str | None = None
    gpu: str | None = None
    driver: str | None = None
    cuda: str | None = None
    python: str | None = None
    commit: str | None = Field(default=None, pattern=COMMIT)
    recipe_hash: str | None = Field(default=None, pattern=SHA256)


class AttemptRecord(StrictModel):
    schema_version: Literal[1] = 1
    attempt_id: str = Field(pattern=SLUG)
    run_id: str = Field(pattern=RUN_ID)
    target_id: str = Field(pattern=SLUG)
    target_profile_sha256: str = Field(pattern=SHA256)
    status: Literal["planned", "running", "succeeded", "failed", "interrupted"]
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    actual: ActualExecution
    output_inventory: FileSnapshot | None


class BackupRecord(StrictModel):
    state: Literal["not-verified"] = "not-verified"
    verified_at: datetime | None = None
    location: str | None = None
    sha256: str | None = Field(default=None, pattern=SHA256)

    @model_validator(mode="after")
    def verification_is_not_available_before_wi_041(self) -> BackupRecord:
        if any(value is not None for value in (self.verified_at, self.location, self.sha256)):
            raise ValueError("backup verification fields are unavailable before WI-041")
        return self


ArtifactRole = Literal[
    "report",
    "metrics",
    "parameters",
    "point-cloud",
    "image",
    "video",
    "checkpoint",
    "log",
    "intermediate",
    "other",
]
Retention = Literal["local-required", "local-selected", "manifest-only"]


class ArtifactRecord(StrictModel):
    artifact_id: str = Field(pattern=r"^art_[0-9a-f]{16}$")
    role: ArtifactRole
    retention: Retention
    source_attempt_id: str = Field(pattern=SLUG)
    relative_path: str | None = None
    size: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern=SHA256)
    remote_source: str | None
    promoted_at: datetime | None
    backup: BackupRecord = Field(default_factory=BackupRecord)

    @field_validator("relative_path")
    @classmethod
    def relative_path_is_safe(cls, value: str | None) -> str | None:
        return None if value is None else _relative_path(value)

    @model_validator(mode="after")
    def storage_fields_match_retention(self) -> ArtifactRecord:
        local_fields = (self.relative_path, self.size, self.sha256, self.promoted_at)
        if self.retention == "manifest-only":
            if any(value is not None for value in local_fields) or not self.remote_source:
                raise ValueError(
                    "manifest-only artifacts require remote_source and no local-copy fields"
                )
        elif any(value is None for value in local_fields):
            raise ValueError("promoted artifacts require path, size, checksum, and time")
        return self


class ArtifactManifest(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=RUN_ID)
    artifacts: list[ArtifactRecord]

    @model_validator(mode="after")
    def artifact_identities_are_unique(self) -> ArtifactManifest:
        identifiers = [artifact.artifact_id for artifact in self.artifacts]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("artifact_id values must be unique within a Run")
        paths = [
            artifact.relative_path
            for artifact in self.artifacts
            if artifact.relative_path is not None
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("local artifact paths must be unique within a Run")
        return self
