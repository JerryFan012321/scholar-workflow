"""Explicit human-readable result selection; omitted payload bytes stay unread."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import ArtifactManifest, AttemptRecord, RunRecord

_MODEL_SUFFIXES = {".safetensors", ".pt", ".pth", ".ckpt", ".pkl", ".pickle", ".onnx",
                   ".gguf", ".bin", ".h5", ".hdf5", ".npz", ".npy"}
_TEXT = {".md", ".txt", ".log", ".out", ".err", ".json", ".jsonl", ".yaml", ".yml",
         ".toml", ".ini", ".cfg", ".csv", ".tsv", ".sh", ".bash", ".zsh", ".py",
         ".js", ".ts", ".c", ".cpp", ".h", ".rs", ".xml", ".ipynb"}
_KINDS = {
    "metrics": {".json", ".csv", ".tsv", ".txt", ".yaml", ".yml"},
    "parameters": {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt", ".csv"},
    "report": {".md", ".txt", ".pdf"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp"},
    "video": {".mp4", ".webm", ".mov"},
    "log": {".log", ".txt", ".jsonl", ".csv", ".tsv", ".out", ".err"},
}
_HUMAN_ROLES = set(_KINDS)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Versioned(_Strict):
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_is_integer(cls, value):
        if type(value) is not int:
            raise ValueError("Result selection version must be an integer")
        return value


def _path(value):
    if (not isinstance(value, str) or not value or value != value.strip()
            or PurePosixPath(value).is_absolute() or "\\" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("Result paths must be clean relative Run paths")
    return value


def _text(value):
    if not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Result selection explanations must be readable text")
    return value


class IncludedResult(_Strict):
    path: str = Field(max_length=4096)
    kind: Literal["metrics", "parameters", "report", "image", "video", "log"]
    purpose: str = Field(min_length=1, max_length=2000)
    _validate_path = field_validator("path")(_path)
    _validate_purpose = field_validator("purpose")(_text)


class DeferredResult(_Strict):
    path: str = Field(max_length=4096)
    reason: str = Field(min_length=1, max_length=2000)
    _validate_path = field_validator("path")(_path)
    _validate_reason = field_validator("reason")(_text)


class ResultSelection(_Versioned):
    include: list[IncludedResult] = Field(max_length=4096)
    defer: list[DeferredResult] = Field(default_factory=list, max_length=4096)

    @model_validator(mode="after")
    def unique_paths(self):
        paths = [row.path for row in (*self.include, *self.defer)]
        if len(paths) != len(set(paths)):
            raise ValueError("Result selection paths must be unique and disjoint")
        return self


class OmittedResult(_Strict):
    source_path: str = Field(max_length=4096)
    artifact_id: str | None = Field(pattern=r"^art_[0-9a-f]{16}$")
    declared_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    declared_size: int | None = Field(ge=0)
    reason: Literal["model", "not-selected", "deferred"]
    explanation: str | None
    _validate_path = field_validator("source_path")(_path)


class ResultDelivery(_Versioned):
    selection: ResultSelection
    omitted: list[OmittedResult] = Field(max_length=10000)
    omitted_byte_verification: Literal["not-performed"] = "not-performed"


def _model(path, artifacts):
    return (PurePosixPath(path).suffix.lower() in _MODEL_SUFFIXES
            or any(row.relative_path == path and row.role == "checkpoint" for row in artifacts.artifacts))


def _required(files, directories, run_id):
    from .collection import _record, _relative

    run = _record(files, "run.yaml", RunRecord)
    required = {"run.yaml", "artifacts.yaml", "report.md", "notes.md"}
    snapshots = [run.entrypoint, run.config, run.environment, run.dataset.manifest]
    for directory in directories:
        if directory.startswith("attempts/") and directory.count("/") == 1:
            required.update((directory + "/attempt.yaml", directory + "/target.yaml"))
            attempt = _record(files, directory + "/attempt.yaml", AttemptRecord)
            if attempt.output_inventory:
                snapshots.append(attempt.output_inventory)
    prefix = f"experiments/{run_id}/"
    for snapshot in snapshots:
        path = _relative(snapshot.path)
        if not path.startswith(prefix):
            raise ValueError("Required evidence is outside the selected Run")
        required.add(_path(path[len(prefix):]))
    return required


def _readable(path, data):
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in _TEXT:
        text = data.decode("utf-8")
        if any(ord(c) < 32 and c not in "\n\r\t" or ord(c) == 127 for c in text):
            raise ValueError("Result text contains binary/control data")
        return
    signatures = {
        ".png": lambda: data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": lambda: data.startswith(b"\xff\xd8"),
        ".jpeg": lambda: data.startswith(b"\xff\xd8"),
        ".gif": lambda: data.startswith((b"GIF87a", b"GIF89a")),
        ".webp": lambda: data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        ".pdf": lambda: data.startswith(b"%PDF-"),
        ".mp4": lambda: data[4:8] == b"ftyp",
        ".mov": lambda: data[4:8] in {b"ftyp", b"wide", b"moov", b"mdat"},
        ".webm": lambda: data.startswith(b"\x1aE\xdf\xa3"),
    }
    if suffix not in signatures or not signatures[suffix]():
        raise ValueError("Unsupported or mismatched readable result format; use a result selection")


def _policy(paths, required, artifacts, selection):
    include = {row.path: row for row in selection.include}
    defer = {row.path: row.reason for row in selection.defer}
    if not (set(include) | set(defer)).issubset(paths):
        raise ValueError("Result selection names an unavailable file")
    if set(defer) & required:
        raise ValueError("Required Run/Attempt context cannot be deferred")
    for path in required | set(include):
        if _model(path, artifacts):
            raise ValueError("Model payload cannot be included as a local result")
        suffix = PurePosixPath(path).suffix.lower()
        if path in include and suffix not in _KINDS[include[path].kind]:
            raise ValueError("Selected result kind does not match a supported file format")
        if path in required and suffix not in _TEXT:
            raise ValueError("Required execution context must be readable text, not a payload")
    for row in artifacts.artifacts:
        if (row.relative_path and row.retention == "local-required" and row.role in _HUMAN_ROLES
                and row.relative_path not in include and row.relative_path not in required
                and row.relative_path not in defer):
            raise ValueError("Required readable result needs selection or explicit deferral")
    return required | set(include)


def _omitted(paths, selected, artifacts, selection):
    artifact_paths = {row.relative_path: row for row in artifacts.artifacts if row.relative_path}
    deferred = {row.path: row.reason for row in selection.defer}
    rows = []
    for path in sorted(paths - selected):
        artifact = artifact_paths.get(path)
        reason = "model" if _model(path, artifacts) else "deferred" if path in deferred else "not-selected"
        rows.append({"source_path": path, "artifact_id": artifact.artifact_id if artifact else None,
                     "declared_sha256": artifact.sha256 if artifact else None,
                     "declared_size": artifact.size if artifact else None, "reason": reason,
                     "explanation": deferred.get(path) if reason == "deferred" else None})
    return rows


def capture_results(root, run_id, selection=None):
    """Read mandatory context and selected results, never omitted payload bytes."""
    from .collection import COLLECTION_RESERVED, _record, _tree

    observations = {}
    def metadata(path):
        return path in {"run.yaml", "artifacts.yaml"} or (
            path.startswith("attempts/") and path.count("/") == 2
            and path.rsplit("/", 1)[1] in {"attempt.yaml", "target.yaml"})
    headers, directories, _ = _tree(root, run_id, include=metadata, observations=observations)
    artifacts = _record(headers, "artifacts.yaml", ArtifactManifest)
    observed_paths = set(observations)
    # A separately staged readable delivery need not contain a checkpoint that
    # the unchanged source artifact record explicitly retains. Its hash stays
    # declared, never byte-verified by this receiver.
    paths = observed_paths | {row.relative_path for row in artifacts.artifacts if row.relative_path}
    for path in paths:
        _path(path)
    if any(path.split("/", 1)[0] in COLLECTION_RESERVED for path in paths | directories):
        raise ValueError("Source contains reserved collection transaction metadata")
    required = _required(headers, directories, run_id)
    if selection is None:
        supported = _TEXT | set().union(*_KINDS.values())
        def check_file(path):
            if _model(path, artifacts) or PurePosixPath(path).suffix.lower() not in supported:
                raise ValueError("Run contains model/unclassified payload; supply an explicit result selection")
        for path in paths:
            check_file(path)
        files, actual_directories, modes = _tree(root, run_id, check_file=check_file)
        if any(files.get(path) != data for path, data in headers.items()):
            raise ValueError("Execution records changed during result inspection")
        for path, data in files.items():
            _readable(path, data)
        return files, actual_directories, modes, None
    spec = ResultSelection.model_validate(selection)
    selected = _policy(paths, required, artifacts, spec)
    current = {}
    files, _directories, modes = _tree(root, run_id, include=selected.__contains__, observations=current)
    if set(current) != observed_paths or any(files.get(path) != data for path, data in headers.items()):
        raise ValueError("Execution inventory changed while selecting results")
    if not selected.issubset(files):
        raise ValueError("Required context or selected result is unavailable")
    for path, data in files.items():
        _readable(path, data)
    kept_directories = {"attempts", "artifacts"}
    for path in files:
        parts = path.split("/")
        kept_directories.update("/".join(parts[:index]) for index in range(1, len(parts)))
    delivery = ResultDelivery(schema_version=1, selection=spec, omitted=_omitted(paths, selected, artifacts, spec))
    return files, kept_directories, modes, delivery.model_dump(mode="json")


def validate_delivery(value, files, directories, run_id, artifacts):
    """Check a stored projection without claiming omitted bytes were received."""
    delivery = ResultDelivery.model_validate(value)
    omitted = [row.model_dump(mode="json") for row in delivery.omitted]
    names = [row["source_path"] for row in omitted]
    if names != sorted(set(names)) or set(names) & set(files):
        raise ValueError("Omitted result paths must be sorted, unique and not received")
    paths = set(files) | set(names)
    required = _required(files, directories, run_id)
    selected = _policy(paths, required, artifacts, delivery.selection)
    if selected != set(files) or omitted != _omitted(paths, selected, artifacts, delivery.selection):
        raise ValueError("Result delivery differs from its exact selection or original artifact records")
    for path, data in files.items():
        _readable(path, data)
    return {row["source_path"]: row for row in omitted}


def load_selection(path):
    """Read one explicitly supplied bounded operator config, without writes."""
    import yaml

    from .collection import _UniqueLoader
    from .layout import open_project_root
    from .reception import _read_file

    if path is None:
        return None
    try:
        with open_project_root(path.parent) as descriptor:
            data, _mode = _read_file(descriptor, path.name, 128 * 1024)
        value = yaml.load(data.decode("utf-8"), Loader=_UniqueLoader)
        return ResultSelection.model_validate(value).model_dump(mode="json")
    except (OSError, UnicodeError, ValueError, RecursionError, yaml.YAMLError) as error:
        raise ValueError("Invalid result selection; use its versioned include/defer config") from error
