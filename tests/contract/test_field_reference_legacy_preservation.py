"""Legacy migration keeps explicit Field references, without editing their owners."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scholar_workflow.hub.field_transaction import FieldTransactionError, FieldTransactionService
from scholar_workflow.hub.paper_placement import PaperPlacementError
from scholar_workflow.knowledge.fields import (
    FieldDefinition,
    FieldService,
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from tests.unit.test_hub_paper_placement import (
    NEW_NOTE,
)
from tests.unit.test_hub_paper_placement import (
    _fixture as placement_fixture,
)

SOURCE = "0374b783-02c8-4230-b789-d5c321b432ba"
FIELD = "62f9a02e-c91c-475c-86ca-f0bd19353c12"
REFERENCES = [{
    "reference_id": "shared-paper",
    "target": {
        "source_id": "f2743ec2-261b-4d37-8585-a318276bce9e",
        "object_id": "paper:zotero:1:ABCDEFGH",
    },
    "purpose": "Compare the selected method without copying its owner.",
}]


def _transaction_fixture(tmp_path: Path, schema_version: int):
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    for name in ("existing", "candidate"):
        (root / name).mkdir(parents=True)
        home = "README.md" if name == "candidate" else "Home.md"
        (root / name / home).write_text(f"# {name}\n", encoding="utf-8")
    state = root / ".scholar-workflow"
    state.mkdir()
    existing = {
        "field_id": FIELD, "title": "Existing", "relative_root": "existing",
        "home": "Home.md", "navigation": [],
    }
    if schema_version == 2:
        existing["references"] = deepcopy(REFERENCES)
    declaration = {"schema_version": schema_version, "source_id": SOURCE, "fields": [existing]}
    (state / "fields.yml").write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    registry = KnowledgeSourceRegistry(tmp_path / "host" / "sources.json")
    registry.save(KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(folder_id="fixture-vault", root=root,
                                    capabilities=["read", "write"])],
        sources=[KnowledgeSourceRegistration(source_id=SOURCE, folder_id="fixture-vault",
                                             capabilities=["read", "write"])],
    ))
    # Valid compact JSON makes the legacy commit's registry-publication branch run.
    registry.path.write_text(json.dumps(json.loads(registry.path.read_text())) + "\n", encoding="utf-8")
    fields = FieldService(registry)
    service = FieldTransactionService(fields, state_root=tmp_path / "recovery")
    preview = fields.preview(root)
    selected = next(row for row in preview.fields if row.relative_root == "candidate")
    return root, fields, service, preview, selected


@pytest.mark.parametrize("schema_version", [1, 2])
def test_field_enrollment_plan_and_commit_preserve_existing_manifest_version_and_references(
    tmp_path: Path, schema_version: int,
) -> None:
    root, fields, service, preview, selected = _transaction_fixture(tmp_path, schema_version)
    original_note = (root / "existing" / "Home.md").read_bytes()
    registry_before = fields.registry.path.read_bytes()
    plan = service.plan(preview.candidate_token, selected.field_id)
    assert plan.conflicts == ()
    assert plan.registry_before_sha256 != plan.registry_after_sha256
    service.apply(plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True)
    declaration = yaml.safe_load((root / ".scholar-workflow" / "fields.yml").read_bytes())
    assert declaration["schema_version"] == schema_version
    assert declaration["source_id"] == SOURCE
    existing = next(row for row in declaration["fields"] if row["field_id"] == FIELD)
    assert existing.get("references", []) == (REFERENCES if schema_version == 2 else [])
    assert (root / "existing" / "Home.md").read_bytes() == original_note
    assert fields.registry.path.read_bytes() != registry_before
    if schema_version == 1:
        assert all("references" not in row for row in declaration["fields"])


@pytest.mark.parametrize("schema_version", [1, 2])
def test_direct_field_confirm_appends_without_changing_existing_version_or_references(
    tmp_path: Path, schema_version: int,
) -> None:
    root, fields, _service, preview, selected = _transaction_fixture(tmp_path, schema_version)
    manifest_path = root / ".scholar-workflow" / "fields.yml"
    before = yaml.safe_load(manifest_path.read_bytes())
    notes_before = {
        name: (root / name).read_bytes()
        for name in ("existing/Home.md", "candidate/README.md")
    }

    result = fields.confirm(preview.candidate_token, selected.field_id)

    after = yaml.safe_load(manifest_path.read_bytes())
    assert result.schema_version == after["schema_version"] == schema_version
    assert result.model_dump(mode="json") == after
    assert after["source_id"] == SOURCE
    assert len(after["fields"]) == 2
    assert after["fields"][0] == before["fields"][0]
    assert after["fields"][1]["field_id"] == selected.field_id
    assert after["fields"][1]["relative_root"] == "candidate"
    assert after["fields"][0].get("references", []) == (REFERENCES if schema_version == 2 else [])
    assert all((root / name).read_bytes() == content for name, content in notes_before.items())
    if schema_version == 1:
        assert all("references" not in row for row in after["fields"])


def _preview_with_references(tmp_path: Path):
    root, _fields, service, preview, selected = _transaction_fixture(tmp_path, 2)
    # Supply an explicit reviewed candidate, independently of preview discovery.
    data = selected.model_dump(mode="json")
    data["references"] = deepcopy(REFERENCES)
    selected = FieldDefinition.model_validate(data)
    preview.fields[:] = [selected]
    return root, service, preview, selected


def test_legacy_field_override_without_reference_field_inherits_reviewed_references(tmp_path: Path) -> None:
    _root, service, preview, selected = _preview_with_references(tmp_path)
    override = selected.model_dump(mode="json")
    override.pop("references")
    plan = service.plan(preview.candidate_token, selected.field_id,
                        field_definition=FieldDefinition.model_validate(override))
    pending = service._plans[plan.plan_token]
    manifest = next(row for row in pending.targets if row.relative_path == ".scholar-workflow/fields.yml")
    declaration = yaml.safe_load(manifest.after)
    actual = next(row for row in declaration["fields"] if row["field_id"] == selected.field_id)
    assert declaration["schema_version"] == 2
    assert actual["references"] == REFERENCES


@pytest.mark.parametrize("change", ["remove", "replace"])
def test_legacy_field_override_cannot_explicitly_remove_or_change_references(tmp_path: Path, change: str) -> None:
    _root, service, preview, selected = _preview_with_references(tmp_path)
    override = selected.model_dump(mode="json")
    override["references"] = [] if change == "remove" else [{**REFERENCES[0], "purpose": "Unapproved change."}]
    with pytest.raises(FieldTransactionError, match="references"):
        service.plan(preview.candidate_token, selected.field_id,
                     field_definition=FieldDefinition.model_validate(override))


def _placement_with_references(tmp_path: Path):
    fixture = placement_fixture(tmp_path)
    path = fixture.vault / ".scholar-workflow" / "fields.yml"
    declaration = yaml.safe_load(path.read_bytes())
    declaration["schema_version"] = 2
    declaration["fields"][0]["references"] = deepcopy(REFERENCES)
    path.write_text(yaml.safe_dump(declaration, sort_keys=False), encoding="utf-8")
    fixture.field = FieldDefinition.model_validate(declaration["fields"][0])
    revised = fixture.revised.model_dump(mode="json")
    revised["references"] = deepcopy(REFERENCES)
    fixture.revised = FieldDefinition.model_validate(revised)
    return fixture, declaration


def test_paper_placement_preserves_schema_two_and_exact_references_without_writes(tmp_path: Path) -> None:
    fixture, before = _placement_with_references(tmp_path)
    manifest = fixture.vault / ".scholar-workflow" / "fields.yml"
    original = manifest.read_bytes()
    expected = deepcopy(before)
    expected["fields"][0]["navigation"][0]["items"] = [NEW_NOTE.removeprefix("field/")]
    expected_bytes = yaml.safe_dump(expected, allow_unicode=True, sort_keys=False).encode()
    plan = fixture.plan()
    changed = next(row for row in plan.files if row.kind == "field-manifest")
    assert changed.after_sha256 == "sha256:" + hashlib.sha256(expected_bytes).hexdigest()
    assert manifest.read_bytes() == original


def test_paper_placement_rejects_reference_removal_during_path_rewrite(tmp_path: Path) -> None:
    fixture, _before = _placement_with_references(tmp_path)
    data = fixture.revised.model_dump(mode="json")
    data.pop("references")
    fixture.revised = FieldDefinition.model_validate(data)
    with pytest.raises(PaperPlacementError, match="exact paper-note substitution"):
        fixture.plan()
