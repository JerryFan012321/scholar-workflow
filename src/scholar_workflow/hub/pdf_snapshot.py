"""Generate explicit, immutable PDF annotation snapshots.

Snapshots are projections of a Zotero-owned PDF plus a specific annotation set.
They never replace the Zotero attachment and are never imported back implicitly.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scholar_workflow.hub.zotflow import AnnotationIR


class AnnotationSnapshotError(RuntimeError):
    """An annotated copy could not be generated without overstating fidelity."""


class UnsupportedAnnotationSnapshot(AnnotationSnapshotError):
    """At least one annotation type cannot be exported losslessly."""


@dataclass(frozen=True)
class AnnotationSnapshotReceipt:
    snapshot_path: Path
    metadata_path: Path
    source_pdf_hash: str
    annotation_set_hash: str
    output_hash: str
    annotation_count: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _content_hash(path: Path, expected: str) -> str:
    algorithm, separator, _digest = expected.partition(":")
    if separator != ":" or algorithm not in {"md5", "sha256"}:
        raise AnnotationSnapshotError("annotation PDF identity uses an unsupported hash")
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{algorithm}:{digest.hexdigest()}"


def _annotation_hash(annotations: list[AnnotationIR]) -> str:
    payload = [row.model_dump(mode="json") for row in annotations]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


class AnnotationSnapshotService:
    """Embed supported Zotero annotations into a new PDF using standard objects."""

    supported_types = frozenset({"highlight", "underline", "note", "ink"})

    def generate(
        self,
        source_pdf: Path,
        destination: Path,
        annotations: list[AnnotationIR],
    ) -> AnnotationSnapshotReceipt:
        try:
            import fitz
        except ImportError as exc:  # pragma: no cover - installation contract
            raise AnnotationSnapshotError(
                "PyMuPDF is unavailable; annotated snapshots are disabled"
            ) from exc
        source = Path(source_pdf).resolve(strict=True)
        target = Path(destination).expanduser()
        if not target.is_absolute():
            raise AnnotationSnapshotError("snapshot destination must be absolute")
        if target.suffix.casefold() != ".pdf":
            raise AnnotationSnapshotError("snapshot destination must end in .pdf")
        if target.exists() or target.is_symlink():
            raise AnnotationSnapshotError("snapshot destination already exists")
        if target.resolve(strict=False) == source:
            raise AnnotationSnapshotError("snapshot may not overwrite its source PDF")
        unsupported = sorted({row.type for row in annotations} - self.supported_types)
        if unsupported:
            raise UnsupportedAnnotationSnapshot(
                "unsupported annotation types: " + ", ".join(unsupported)
            )
        if not annotations:
            raise AnnotationSnapshotError("annotation snapshot requires at least one annotation")
        source_hash = _sha256_file(source)
        expected_hashes: set[str] = set()
        pdf_identities: set[tuple[str, str, str]] = set()
        for row in annotations:
            if row.source_pdf_hash != row.pdf_ref.content_hash:
                raise AnnotationSnapshotError("annotation set belongs to a different PDF")
            expected_hashes.add(row.pdf_ref.content_hash)
            pdf_identities.add(
                (
                    row.pdf_ref.library_id,
                    row.pdf_ref.attachment_key,
                    row.pdf_ref.content_hash,
                )
            )
        if len(expected_hashes) > 1:
            raise AnnotationSnapshotError("annotation set mixes multiple source PDFs")
        if len(pdf_identities) != 1:
            raise AnnotationSnapshotError("annotation set mixes multiple PDF identities")
        for expected_hash in expected_hashes:
            if _content_hash(source, expected_hash) != expected_hash:
                raise AnnotationSnapshotError("source PDF hash no longer matches Zotero")
        annotation_hash = _annotation_hash(annotations)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
        metadata = target.with_suffix(target.suffix + ".snapshot.json")
        if metadata.exists() or metadata.is_symlink():
            raise AnnotationSnapshotError("snapshot metadata destination already exists")
        document = fitz.open(source)
        added = 0
        try:
            for row in annotations:
                if row.page_index is None or row.page_index >= document.page_count:
                    raise AnnotationSnapshotError(
                        f"annotation {row.annotation_id} has no valid page"
                    )
                page = document[row.page_index]
                annotation = self._add_annotation(fitz, page, row)
                annotation.set_info(
                    title=row.author or "Zotero",
                    content=row.comment or row.quoted_text,
                    subject=f"Zotero {row.type} · {row.annotation_id}",
                )
                if row.color:
                    color = self._rgb(row.color)
                    if color is not None:
                        annotation.set_colors(stroke=color)
                annotation.update()
                added += 1
            document.save(temporary, garbage=4, deflate=True)
        except Exception:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise
        finally:
            document.close()
        try:
            os.link(temporary, target)
            output_hash = _sha256_file(target)
            pdf_ref = annotations[0].pdf_ref
            self._write_metadata(
                metadata,
                {
                    "schema_version": 1,
                    "pdf_ref": pdf_ref.model_dump(mode="json"),
                    "source_pdf_hash": source_hash,
                    "annotation_set_hash": annotation_hash,
                    "output_hash": output_hash,
                    "annotation_count": added,
                    "supported_types": sorted(self.supported_types),
                    "omitted_types": [],
                    "authority": "zotero",
                    "import_back": False,
                },
            )
        except FileExistsError as exc:
            raise AnnotationSnapshotError("snapshot destination already exists") from exc
        except Exception:
            target.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
            raise
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        with fitz.open(target) as verified:
            actual = sum(1 for page in verified for _annotation in page.annots() or ())
        if actual < added:
            target.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
            raise AnnotationSnapshotError("snapshot verification lost annotations")
        return AnnotationSnapshotReceipt(
            snapshot_path=target,
            metadata_path=metadata,
            source_pdf_hash=source_hash,
            annotation_set_hash=annotation_hash,
            output_hash=output_hash,
            annotation_count=added,
        )

    @classmethod
    def _add_annotation(cls, fitz: Any, page: Any, row: AnnotationIR) -> Any:
        geometry = row.geometry
        page_height = float(page.rect.height)
        if row.type in {"highlight", "underline"}:
            rects = geometry.get("rects")
            if not isinstance(rects, list) or not rects:
                raise AnnotationSnapshotError(
                    f"annotation {row.annotation_id} has no text rectangles"
                )
            quads = [cls._rect(fitz, rect, page_height) for rect in rects]
            if row.type == "highlight":
                return page.add_highlight_annot(quads)
            return page.add_underline_annot(quads)
        if row.type == "note":
            rects = geometry.get("rects")
            if isinstance(rects, list) and rects:
                rectangle = cls._rect(fitz, rects[0], page_height)
                point = fitz.Point(rectangle.x0, rectangle.y0)
            else:
                point = fitz.Point(36, 36)
            return page.add_text_annot(point, row.comment or row.quoted_text or "Zotero note")
        if row.type == "ink":
            paths = geometry.get("paths")
            if not isinstance(paths, list) or not paths:
                raise AnnotationSnapshotError(
                    f"annotation {row.annotation_id} has no ink paths"
                )
            strokes: list[list[tuple[float, float]]] = []
            for path in paths:
                if not isinstance(path, list) or len(path) < 2:
                    raise AnnotationSnapshotError(
                        f"annotation {row.annotation_id} has invalid ink geometry"
                    )
                stroke: list[tuple[float, float]] = []
                for point in path:
                    if not isinstance(point, list) or len(point) != 2:
                        raise AnnotationSnapshotError(
                            f"annotation {row.annotation_id} has invalid ink point"
                        )
                    if any(type(value) not in (int, float) for value in point):
                        raise AnnotationSnapshotError(
                            f"annotation {row.annotation_id} has invalid ink point"
                        )
                    x, y = (float(value) for value in point)
                    if not math.isfinite(x) or not math.isfinite(y):
                        raise AnnotationSnapshotError(
                            f"annotation {row.annotation_id} has invalid ink point"
                        )
                    converted = fitz.Point(x, y) * page.transformation_matrix
                    if not math.isfinite(converted.x) or not math.isfinite(converted.y):
                        raise AnnotationSnapshotError(
                            f"annotation {row.annotation_id} has invalid ink point"
                        )
                    stroke.append((converted.x, converted.y))
                strokes.append(stroke)
            return page.add_ink_annot(strokes)
        raise UnsupportedAnnotationSnapshot(f"unsupported annotation type: {row.type}")

    @staticmethod
    def _rect(fitz: Any, raw: Any, page_height: float) -> Any:
        if not isinstance(raw, list) or len(raw) != 4:
            raise AnnotationSnapshotError("invalid annotation rectangle")
        x0, y0, x1, y1 = (float(value) for value in raw)
        return fitz.Rect(x0, page_height - y1, x1, page_height - y0)

    @staticmethod
    def _rgb(value: str) -> tuple[float, float, float] | None:
        match = re.fullmatch(r"#([0-9a-fA-F]{6})", value)
        if match is None:
            return None
        number = int(match.group(1), 16)
        return (
            ((number >> 16) & 255) / 255,
            ((number >> 8) & 255) / 255,
            (number & 255) / 255,
        )

    @staticmethod
    def _write_metadata(path: Path, payload: dict[str, Any]) -> None:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())


__all__ = [
    "AnnotationSnapshotError",
    "AnnotationSnapshotReceipt",
    "AnnotationSnapshotService",
    "UnsupportedAnnotationSnapshot",
]
