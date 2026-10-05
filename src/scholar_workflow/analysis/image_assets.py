"""Explicit selected-image dependencies, shared by commit and reproduction."""

from __future__ import annotations

import struct
import zlib
from collections.abc import Callable
from hashlib import sha256
from pathlib import PurePosixPath

from ruamel.yaml import YAML

from scholar_workflow.analysis.models import AnalysisDocument, CanvasImage
from scholar_workflow.knowledge.catalog_models import HubAsset


class ImageAssetError(ValueError):
    """A declared image is absent, changed, unsafe or not owned by this analysis."""


def document_images(document: AnalysisDocument) -> list[CanvasImage]:
    return [record.canvas_image for claim in document.claims for record in (claim, *claim.points)
            if record.canvas_image is not None]


def image_manifest(payload: bytes) -> list[HubAsset]:
    try:
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError("oversized manifest")
        value = YAML(typ="safe").load(payload.decode("utf-8"))
        if (not isinstance(value, dict) or set(value) != {"schema_version", "assets"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or not isinstance(value["assets"], list)):
            raise ValueError("invalid manifest shape")
        rows = [HubAsset.model_validate(row) for row in value["assets"]]
        if len({row.asset_id for row in rows}) != len(rows) or len({row.vault_path for row in rows}) != len(rows):
            raise ValueError("duplicate image asset identity or path")
        return rows
    except Exception as exc:
        raise ImageAssetError("Canvas images require a valid explicit assets manifest") from exc


def verify_png(image: CanvasImage, payload: bytes) -> None:
    if len(payload) > 64 * 1024 * 1024 or sha256(payload).hexdigest() != image.sha256:
        raise ImageAssetError("Canvas image bytes differ from the supplied hash")
    if payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise ImageAssetError("Canvas image is not a PNG")
    offset, dimensions, has_data, ended = 8, None, False, False
    while offset + 12 <= len(payload):
        size = struct.unpack(">I", payload[offset:offset + 4])[0]
        end = offset + size + 12
        if end > len(payload):
            raise ImageAssetError("Canvas PNG has a truncated chunk")
        kind = payload[offset + 4:offset + 8]
        data = payload[offset + 8:end - 4]
        crc = struct.unpack(">I", payload[end - 4:end])[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != crc:
            raise ImageAssetError("Canvas PNG chunk integrity failed")
        if offset == 8:
            if kind != b"IHDR" or size != 13:
                raise ImageAssetError("Canvas PNG requires a valid initial IHDR")
            dimensions = struct.unpack(">II", data[:8])
        elif kind == b"IHDR":
            raise ImageAssetError("Canvas PNG has a repeated IHDR")
        has_data |= kind == b"IDAT"
        offset = end
        if kind == b"IEND":
            ended = size == 0 and end == len(payload)
            break
    if not ended or not has_data or dimensions != (image.pixel_width, image.pixel_height):
        raise ImageAssetError("Canvas PNG dimensions or complete chunk structure differ")


def verify_canvas_assets(
    document: AnalysisDocument, paper_folder: PurePosixPath,
    assets: list[HubAsset], read: Callable[[str], bytes],
) -> dict[str, str]:
    """Read only explicit owned paths; do not infer assets from an embed or name."""
    by_id = {asset.asset_id: asset for asset in assets}
    if len(by_id) != len(assets) or len({asset.vault_path for asset in assets}) != len(assets):
        raise ImageAssetError("Duplicate selected-image asset identity or path")
    result = {}
    for image in document_images(document):
        path = (paper_folder / image.image_path).as_posix()
        asset = by_id.get(image.asset_id)
        if (asset is None or asset.vault_path != path
                or document.artifact_id not in asset.owner_artifact_ids
                or asset.sha256 != "sha256:" + image.sha256 or asset.media_type != "image/png"):
            raise ImageAssetError("Canvas image is not explicitly owned at its paper-local path and hash")
        payload = read(path)
        if len(payload) != asset.size:
            raise ImageAssetError("Canvas image size differs from its asset declaration")
        verify_png(image, payload)
        result[path] = asset.sha256
    return result
