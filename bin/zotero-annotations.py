#!/usr/bin/env python3
"""Export one paper's annotations through the Zotero Local API."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from scholar_workflow.adapters.zotero_local import (
    ZoteroLocalAdapter,
    ZoteroLocalError,
    ZoteroLocalUnavailable,
)
from scholar_workflow.workflows.annotations import (
    AnnotationAmbiguous,
    AnnotationExportError,
    extract_annotation_export,
    to_markdown,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", help="paper title fragment")
    parser.add_argument("--item", help="Zotero item key (skip title search)")
    parser.add_argument("--json", action="store_true")
    return parser


def _print_export(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    rows = payload["annotations"]
    counts: dict[str, int] = {}
    for row in rows:
        kind = str(row["type"])
        counts[kind] = counts.get(kind, 0) + 1
    summary = " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    print(
        f"item={payload['item_key']} attachment={payload['attachment_key']} "
        f"total={payload['count']}{f' {summary}' if summary else ''}"
    )
    rendered = to_markdown(rows)
    if rendered:
        print(rendered)


def run(argv: list[str] | None = None, *, adapter_factory=ZoteroLocalAdapter) -> int:
    args = _parser().parse_args(argv)
    if args.query is None and args.item is None:
        _parser().error("provide a title fragment or --item ITEM_KEY")
    try:
        with adapter_factory() as adapter:
            payload = extract_annotation_export(
                adapter,
                query=args.query,
                item_key=args.item,
            )
    except AnnotationAmbiguous as exc:
        print(str(exc), file=sys.stderr)
        return 5
    except (AnnotationExportError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ZoteroLocalUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except ZoteroLocalError as exc:
        print(str(exc), file=sys.stderr)
        return 8
    _print_export(payload, as_json=args.json)
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
