"""Digest-bound local Source/Field registration using the existing authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from scholar_workflow.knowledge.fields import FieldManifest, FieldRegistryError, FieldService
from scholar_workflow.knowledge.presentation import _text


@dataclass(frozen=True)
class RegistrationPlan:
    payload: dict
    candidate_token: str
    selected_id: str


def registration_plan(
    service: FieldService, root: Path, *, field_root: str | None, existing_source: bool
) -> RegistrationPlan:
    if (field_root is None) == (not existing_source):
        raise FieldRegistryError("Select exactly one --field-root or --existing-source")
    preview = service.preview(root)
    candidate = service.candidates.peek(preview.candidate_token)
    if existing_source:
        if not preview.registration_only:
            raise FieldRegistryError("Existing Source is not awaiting host registration")
        selected = preview.registered_fields
        selected_id = preview.source_id
        reasons = []
    else:
        if preview.registration_only:
            raise FieldRegistryError("Existing portable manifest requires --existing-source")
        selected = [row for row in preview.fields if row.relative_root == field_root]
        if len(selected) != 1:
            raise FieldRegistryError("Select exactly one Field relative root from knowledge preview")
        selected_id = selected[0].field_id
        reasons = service.registration_reasons(preview.candidate_token, selected_id)
    # UUIDs minted by preview are provisional. Bind every semantic choice and
    # current byte revision, not random IDs that change between CLI processes.
    fields = [row.model_dump(mode="json", exclude=set() if existing_source else {"field_id"})
              for row in selected]
    payload = {
        "schema_version": 1,
        "mode": "existing-source" if existing_source else "single-field",
        "root": str(candidate.root),
        "root_identity": list(candidate.root_identity),
        "content_base_hash": candidate.content_base_hash,
        "manifest_base_hash": preview.manifest_base_hash,
        "registry_base_hash": preview.registry_base_hash,
        "source_id": preview.source_id if preview.existing_manifest else None,
        "fields": fields,
        "existing_fields": [row.model_dump(mode="json") for row in preview.registered_fields],
        "conflicts": preview.conflicts,
        "transaction_reasons": reasons,
        "external_managed_documents": [row.model_dump(mode="json")
                                       for row in preview.external_managed_documents],
        "unmapped_markdown": preview.unmapped_markdown,
        "status": "blocked" if preview.conflicts or reasons else "ready-for-confirmation",
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    payload["approved_digest"] = hashlib.sha256(encoded).hexdigest()
    return RegistrationPlan(payload, preview.candidate_token, selected_id)


def register(
    service: FieldService, root: Path, *, field_root: str | None,
    existing_source: bool, approved_digest: str,
) -> FieldManifest:
    if re.fullmatch(r"[0-9a-f]{64}", approved_digest) is None:
        raise FieldRegistryError("approved digest must be a SHA-256 hex value")
    plan = registration_plan(service, root, field_root=field_root, existing_source=existing_source)
    if plan.payload["approved_digest"] != approved_digest:
        raise FieldRegistryError("Registration plan changed; review a fresh plan before confirming")
    if plan.payload["status"] != "ready-for-confirmation":
        raise FieldRegistryError("Registration is blocked; legacy content requires joint transaction review")
    if existing_source:
        return service.confirm_source(plan.candidate_token, plan.selected_id)
    return service.confirm(plan.candidate_token, plan.selected_id)


def plan_markdown(payload: dict, *, language: str) -> str:
    zh = language == "zh"
    lines = ["# 知识目录登记方案" if zh else "# Knowledge registration plan", "",
             ("尚未登记；正文、图和身份清单均未改写。" if zh else
              "Not registered; no prose, Canvas or identity manifest has been changed."), "",
             f"{'状态' if zh else 'Status'}: " + (
                 ("待确认" if zh else "Ready for confirmation")
                 if payload["status"] == "ready-for-confirmation" else ("受阻" if zh else "Blocked")), "",
             ("仅登记已有便携 Source；保留全部既有 Field 身份，不改清单。" if zh else
              "Attach the existing portable Source; preserve all Field identities and its manifest.")
             if payload["mode"] == "existing-source" else
             ("只登记以下单个领域；不创建首页，不登记兄弟目录。" if zh else
              "Register only the selected Field; no new homepage or sibling registration."), ""]
    for field in payload["fields"]:
        lines += [f"## {_text(field['title'])}", "",
                  f"- {'相对目录' if zh else 'Relative root'}: {_text(field['relative_root'])}",
                  f"- {'已有入口' if zh else 'Existing home'}: {_text(field['home'])}", ""]
        for group in field["navigation"]:
            lines += [f"### {_text(group['label'])}", ""]
            lines += [f"- {_text(item)}" for item in group["items"]]
            lines.append("")
    lines += ["## 约束与事务诊断" if zh else "## Constraints and transaction diagnostics", ""]
    findings = payload["conflicts"] + payload["transaction_reasons"]
    lines += [f"- {_text(item)}" for item in findings] if findings else ["无。" if zh else "None."]
    lines += ["", "## 确认凭证" if zh else "## Confirmation digest", "",
              f"`{payload['approved_digest']}`", "",
              ("确认仅表示目录登记，不表示论文科学支持、Canvas 审美或旧稿迁移通过。" if zh else
               "Confirmation grants registration only, not scientific, visual or migration acceptance."), ""]
    return "\n".join(lines)


def fields_markdown(fields: list[dict], *, language: str) -> str:
    zh = language == "zh"
    lines = ["# 已登记知识领域" if zh else "# Registered knowledge Fields", ""]
    if not fields:
        lines += ["尚无已登记领域。" if zh else "No registered Fields.", ""]
    for field in fields:
        if not field["available"]:
            lines += ["- " + _text(str(field["detail"])), ""]
            continue
        lines += [f"## {_text(str(field['title']))}", "",
                  f"- {'已有入口' if zh else 'Existing home'}: {_text(str(field['home']))}", ""]
        for group in field["navigation"]:
            lines += [f"### {_text(group['label'])}", ""]
            lines += [f"- {_text(item)}" for item in group["items"]]
            lines.append("")
    return "\n".join(lines)
