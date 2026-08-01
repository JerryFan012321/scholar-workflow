"""Configuration loading and validation."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import os
import yaml
from pydantic import BaseModel, field_validator


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


class Config(BaseModel):
    version: int = 1
    papers_root: Path
    paper_inbox: Path = DEFAULT_PAPER_INBOX
    vault_root: Path
    env_records_root: Path = DEFAULT_ENV_RECORDS_ROOT
    obsidian: ObsidianConfig = ObsidianConfig()
    notion: NotionConfig = NotionConfig()
    link_service: LinkServiceConfig = LinkServiceConfig()
    policy: PolicyConfig = PolicyConfig()

    @field_validator("papers_root", "paper_inbox", "vault_root", "env_records_root", mode="before")
    @classmethod
    def expand_path(cls, v: Any) -> Path:
        return Path(os.path.expandvars(str(v))).expanduser().resolve()


def load_config(path: Path | None = None) -> Config:
    home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
    cfg_path = path or home / "config.yml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config not found: {cfg_path}")
    with cfg_path.open() as f:
        data = yaml.safe_load(f)
    return Config(**data)
