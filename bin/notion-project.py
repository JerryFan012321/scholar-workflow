#!/usr/bin/env python3
"""Push a two-DB Notion projection from a prepared JSON payload (skill mechanical layer).

Reads stdin JSON {papers:[...], related_docs:[...]} that the host LLM assembled from
zotero-mcp fields, then upserts it into the two-DB model (GOALS INV21): papers into the
Papers DB keyed by Resource ID, related docs into the Related Docs DB keyed by Doc ID with
a Paper relation back to their paper. Papers go first so each doc's relation resolves to a
real page_id. Prints {papers:{resource_id:page_id}, related_docs:{doc_id:page_id}} so the
caller (SKILL.md) can assemble the topic page with those ids.

This is NOT wired into the CLI — the CLI never makes outbound network calls. It reuses the
contract-tested NotionAdapter library. Token comes from SCHOLAR_WORKFLOW_NOTION_TOKEN
(never a flag/config/git). DB ids come from config (notion.*), overridable via the payload.

Payload shape:
  {
    "papers": [
      {"resource_id": "arxiv:2409.17106", "fields": {<notion property dict>}}, ...
    ],
    "related_docs": [
      {"doc_id": "paper/.../X论文相关资料.md",
       "paper_resource_id": "arxiv:2409.17106",   # links Paper relation via the map
       "fields": {<notion property dict, minus Paper>}}, ...
    ]
  }
Fields are raw Notion property objects (e.g. {"Name": {"title": [...]}}) so the caller
keeps full control; the script only injects the upsert key and the Paper relation.
"""
from __future__ import annotations
import json
import os
import sys

from scholar_workflow.config import load_config
from scholar_workflow.adapters.notion import NotionAdapter

TOKEN_ENV = "SCHOLAR_WORKFLOW_NOTION_TOKEN"


def _die(msg: str, code: int) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def main() -> None:
    token = os.environ.get(TOKEN_ENV)
    if not token:
        _die(f"{TOKEN_ENV} not set", 3)  # dependency not ready (AGENT.md exit codes)

    payload = json.load(sys.stdin)
    papers = payload.get("papers", [])
    related = payload.get("related_docs", [])

    cfg = load_config().notion
    papers_ds = payload.get("papers_data_source_id") or cfg.data_source_id
    related_ds = payload.get("related_docs_data_source_id") or cfg.related_docs_data_source_id
    if papers and not papers_ds:
        _die("no papers data_source_id (config notion.data_source_id or payload)", 2)
    if related and not related_ds:
        _die("no related_docs data_source_id (config notion.related_docs_data_source_id "
             "or payload)", 2)

    adapter = NotionAdapter(token=token, api_version=cfg.api_version)
    paper_ids: dict[str, str] = {}
    doc_ids: dict[str, str] = {}
    try:
        # Papers first — their page_ids are the relation targets for related docs.
        for p in papers:
            rid = p["resource_id"]
            paper_ids[rid] = adapter.upsert_page(papers_ds, rid, dict(p.get("fields", {})))

        for d in related:
            did = d["doc_id"]
            fields = dict(d.get("fields", {}))
            link_rid = d.get("paper_resource_id")
            if link_rid:
                target = paper_ids.get(link_rid)
                if not target:
                    _die(f"related doc {did!r} links unknown paper {link_rid!r}", 2)
                fields["Paper"] = {"relation": [{"id": target}]}
            doc_ids[did] = adapter.upsert_page(related_ds, did, fields,
                                               key_property="Doc ID")
    finally:
        adapter.close()

    json.dump({"papers": paper_ids, "related_docs": doc_ids},
              sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
