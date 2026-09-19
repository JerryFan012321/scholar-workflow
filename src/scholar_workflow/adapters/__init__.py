"""Adapters package.

Zotero metadata, existence, indexed full text, and writes use the loopback Local API.
Other adapters span network and filesystem: arXiv PDF fetch writes to the inbox, Notion
projection reaches its declared external service, and Obsidian managed blocks plus the
local link service remain filesystem-only.
"""
