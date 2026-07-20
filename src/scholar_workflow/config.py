"""Configuration loading and validation."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import os
import yaml
from pydantic import BaseModel, field_validator


DEFAULT_HOME = Path.home() / ".config" / "scholar-workflow"
DEFAULT_PAPER_INBOX = Path.home() / "documents" / "0-inbox" / "paper-inbox"


class ZoteroConfig(BaseModel):
    local_api_url: str = "http://127.0.0.1:23119/api"


class ObsidianConfig(BaseModel):
    cli_command: str = "obsidian"
    direct_file_fallback: bool = True
    managed_block_start: str = "<!-- scholar-workflow:start -->"
    managed_block_end: str = "<!-- scholar-workflow:end -->"


class NotionConfig(BaseModel):
    enabled: bool = False
    file_upload: bool = False
    preserve_human_content: bool = True


class PolicyConfig(BaseModel):
    paper_pdf_source: str = "arxiv_only"
    require_approval_for_download: bool = True
    notion_file_upload: bool = False


class Config(BaseModel):
    version: int = 1
    papers_root: Path
    paper_inbox: Path = DEFAULT_PAPER_INBOX
    vault_root: Path
    zotero: ZoteroConfig = ZoteroConfig()
    obsidian: ObsidianConfig = ObsidianConfig()
    notion: NotionConfig = NotionConfig()
    policy: PolicyConfig = PolicyConfig()

    @field_validator("papers_root", "paper_inbox", "vault_root", mode="before")
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
