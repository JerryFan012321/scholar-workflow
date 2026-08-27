"""Configuration loading and validation."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Union, get_args, get_origin
import io
import os
import types
import yaml
from pydantic import BaseModel, field_validator
from ruamel.yaml import YAML


class ConfigNotFound(FileNotFoundError):
    """config.yml is absent. Distinct so callers (doctor) can degrade gracefully
    instead of crashing. Subclasses FileNotFoundError for backward compatibility."""


class ConfigError(ValueError):
    """User-facing config problem (unknown/secret key, bad value, init conflict).
    CLI maps this to exit 2."""


DEFAULT_HOME = Path.home() / ".config" / "scholar-workflow"
DEFAULT_PAPER_INBOX = Path.home() / "documents" / "0-inbox" / "paper-inbox"
DEFAULT_ENV_RECORDS_ROOT = Path.home() / "dev" / "env-records"


class ObsidianConfig(BaseModel):
    cli_command: str = "obsidian"
    direct_file_fallback: bool = True
    managed_block_start: str = "<!-- scholar-workflow:start -->"
    managed_block_end: str = "<!-- scholar-workflow:end -->"


class NotionConfig(BaseModel):
    enabled: bool = False
    file_upload: bool = False
    preserve_human_content: bool = True
    # Data-source model (breaking change 2025-09-03): rows live in a data source.
    # database_id is kept only for reference/jump links; the API uses data_source_id.
    # Two-DB model: Papers DB (keyed by Resource ID) + Related Docs DB (keyed by
    # Doc ID, relation-linked back to a paper). database_id/data_source_id target
    # Papers; related_docs_* target the companion DB. All optional until wired live.
    database_id: str | None = None
    data_source_id: str | None = None
    related_docs_database_id: str | None = None
    related_docs_data_source_id: str | None = None
    api_version: str = "2026-03-11"


NOTION_TOKEN_ENV = "SCHOLAR_WORKFLOW_NOTION_TOKEN"


def notion_token() -> str | None:
    """Read the Notion integration token from the environment (never from config/git)."""
    return os.environ.get(NOTION_TOKEN_ENV)


class LinkServiceConfig(BaseModel):
    port: int = 23128
    storage_root: Path = Path.home() / "Zotero" / "storage"

    @field_validator("storage_root", mode="before")
    @classmethod
    def _expand(cls, v: Any) -> Path:
        return Path(os.path.expandvars(str(v))).expanduser().resolve()


class PolicyConfig(BaseModel):
    paper_pdf_source: str = "arxiv_only"
    require_approval_for_download: bool = True
    notion_file_upload: bool = False


class RecommendConfig(BaseModel):
    """recommend-papers preferences (feature-ai-reading). Two-layer: this global
    layer lives in recommend.yml; a per-cwd project layer overlays keywords/watchlist.
    Not credentials — session cookies/tokens stay in env vars / env-records."""
    interests: list[str] = []
    sources: dict[str, bool] = {
        "s2_recommendations": True,
        "scholar_inbox": True,
        "s2_author": True,
        "hf_daily": True,
    }
    daily_limit: int = 15
    min_score: float = 0.0
    notebooklm_classification: str = "auto_topic"
    watchlist: list[str] = []  # S2 authorIds (semi-auto registered)


class Config(BaseModel):
    version: int = 1
    paper_inbox: Path = DEFAULT_PAPER_INBOX
    research_vault_root: Path
    env_records_root: Path = DEFAULT_ENV_RECORDS_ROOT
    obsidian: ObsidianConfig = ObsidianConfig()
    notion: NotionConfig = NotionConfig()
    link_service: LinkServiceConfig = LinkServiceConfig()
    policy: PolicyConfig = PolicyConfig()

    @field_validator("paper_inbox", "research_vault_root", "env_records_root", mode="before")
    @classmethod
    def expand_path(cls, v: Any) -> Path:
        return Path(os.path.expandvars(str(v))).expanduser().resolve()


SECRET_KEY_MARKERS = ("token", "api_key", "cookie", "secret", "password")


def config_path() -> Path:
    """Resolve config.yml's path without requiring it to exist."""
    home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
    return home / "config.yml"


def load_config(path: Path | None = None) -> Config:
    cfg_path = path or config_path()
    if not cfg_path.exists():
        raise ConfigNotFound(f"Config not found: {cfg_path}")
    with cfg_path.open() as f:
        data = yaml.safe_load(f)
    return Config(**data)


def _unwrap_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is Union or origin is getattr(types, "UnionType", ()):
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _is_secret_key(key: str) -> bool:
    return any(m in key.lower() for m in SECRET_KEY_MARKERS)


def _resolve_field(key: str) -> Any:
    """Resolve a dotted key against the Config schema, returning its annotation.
    Raises ConfigError for unknown keys — the schema is never copied into a skill."""
    parts = key.split(".")
    model: Any = Config
    annotation: Any = None
    for i, part in enumerate(parts):
        fields = getattr(model, "model_fields", {})
        if part not in fields:
            raise ConfigError(f"Unknown config key: {key!r}")
        annotation = fields[part].annotation
        if i < len(parts) - 1:
            if not (isinstance(annotation, type) and issubclass(annotation, BaseModel)):
                raise ConfigError(f"Unknown config key: {key!r}")
            model = annotation
    return annotation


def _coerce(value: str, annotation: Any) -> Any:
    ann = _unwrap_optional(annotation)
    if ann is bool:
        low = value.strip().lower()
        if low == "true":
            return True
        if low == "false":
            return False
        raise ConfigError(f"Expected true or false, got {value!r}")
    if ann is int:
        try:
            return int(value.strip())
        except ValueError:
            raise ConfigError(f"Expected an integer, got {value!r}") from None
    return value  # str / Path — validators expand paths at load time


def _secret_msg(key: str) -> str:
    return (f"{key!r} looks like a secret and must never live in config.yml or git. "
            f"Set it as an environment variable instead "
            f"(e.g. {NOTION_TOKEN_ENV} for the Notion token).")


def _set_nested(data: dict, key: str, value: Any) -> None:
    parts = key.split(".")
    node = data
    for part in parts[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.default_flow_style = False
    return y


def _atomic_write(cfg_path: Path, payload: bytes) -> None:
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg_path.with_name(cfg_path.name + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, cfg_path)


def init_config(research_vault_root: str, extra: dict[str, str] | None = None,
                path: Path | None = None) -> Path:
    """Write a minimal config.yml (version + vault + explicit extras only, never all
    defaults). Idempotent: identical re-init is a no-op; a differing existing file is
    an error (no --force). Validates the candidate before an atomic replace."""
    cfg_path = path or config_path()
    data: dict[str, Any] = {"version": 1, "research_vault_root": research_vault_root}
    for k, raw in (extra or {}).items():
        if _is_secret_key(k):
            raise ConfigError(_secret_msg(k))
        _set_nested(data, k, _coerce(raw, _resolve_field(k)))
    Config(**data)  # validate; raises pydantic ValidationError on bad input
    buf = io.BytesIO()
    _yaml().dump(data, buf)
    payload = buf.getvalue()
    if cfg_path.exists():
        if cfg_path.read_bytes() == payload:
            return cfg_path
        raise ConfigError(
            f"Config already exists at {cfg_path} with different content; "
            "edit it with `config set KEY VALUE` instead of re-initializing.")
    _atomic_write(cfg_path, payload)
    return cfg_path


def set_config_value(key: str, value: str, path: Path | None = None) -> Any:
    """Set one dotted key in config.yml, preserving comments/formatting (round-trip).
    Rejects unknown and secret keys before touching the file; validates the full
    candidate config before an atomic replace. Returns the coerced value."""
    cfg_path = path or config_path()
    if not cfg_path.exists():
        raise ConfigNotFound(f"Config not found: {cfg_path}")
    if _is_secret_key(key):
        raise ConfigError(_secret_msg(key))
    coerced = _coerce(value, _resolve_field(key))
    y = _yaml()
    with cfg_path.open() as f:
        data = y.load(f) or {}
    _set_nested(data, key, coerced)
    Config(**data)  # validate full candidate
    buf = io.BytesIO()
    y.dump(data, buf)
    _atomic_write(cfg_path, buf.getvalue())
    return coerced


def load_recommend_config(cwd: Path | None = None) -> RecommendConfig:
    """Load the two-layer recommend-papers config: global recommend.yml, overlaid by
    projects/<cwd-name>.yml when present. Project keywords/watchlist are additive
    (extend, not replace); other project keys override. Missing global returns defaults."""
    home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
    data: dict[str, Any] = {}
    global_path = home / "recommend.yml"
    if global_path.exists():
        with global_path.open() as f:
            data = yaml.safe_load(f) or {}

    proj_name = (cwd or Path.cwd()).name
    proj_path = home / "projects" / f"{proj_name}.yml"
    if proj_path.exists():
        with proj_path.open() as f:
            overlay = yaml.safe_load(f) or {}
        for key, val in overlay.items():
            if key in ("interests", "watchlist") and isinstance(val, list):
                data[key] = list(dict.fromkeys([*data.get(key, []), *val]))
            else:
                data[key] = val

    return RecommendConfig(**data)
