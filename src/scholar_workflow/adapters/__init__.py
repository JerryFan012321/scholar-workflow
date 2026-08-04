"""Adapters package.

Metadata, existence, and semantic recall are authoritative from zotero-mcp, orchestrated
by the host LLM at the skill layer — the CLI is a separate subprocess and cannot reach
MCP (INV16/INV18). What these adapters do NOT touch is Zotero: import into the library
happens via zotero-mcp (`write_item` import), driven by the host LLM, never here. Their
own work spans both network and filesystem: arXiv PDF fetch (network) to the inbox and
Notion projections (network) reach declared external services; Obsidian managed blocks
and the local link service are filesystem-only.
"""
