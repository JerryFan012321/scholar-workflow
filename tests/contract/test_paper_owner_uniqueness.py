from __future__ import annotations

import json
import os
import shutil
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scholar_workflow.analysis.apply_changes import (
    KnowledgeApplyReceipt,
    KnowledgeProviderSnapshot,
    _hash_payload,
)
from scholar_workflow.knowledge.catalog_models import HubCatalog
from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)
from scholar_workflow.knowledge.registration import registration_plan
from scholar_workflow.workflows.register_paper import paper_plan, register_paper
from scholar_workflow.workflows.register_source import register_source


class LocalZotero:
    """Fixed synthetic identity; no real API client is constructed."""

    def __init__(self, pdf: Path, library_id: int = 123):
        self.pdf = pdf
        self.library_id = library_id

    def get_item(self, key):
        data = (
            {"itemType": "preprint", "title": "Synthetic paper"}
            if key == "ABCD2345" else
            {"itemType": "attachment", "parentItem": "ABCD2345",
             "contentType": "application/pdf", "linkMode": "imported_file"}
        )
        return {"key": key, "library": {"id": self.library_id, "type": "user"}, "data": data}

    def resolve_attachment_locator(self, key):
        return SimpleNamespace(path=self.pdf, attachment_key=key, library_id=str(self.library_id))


def _register_source(root, registry):
    root.mkdir()
    (root / "README.md").write_text("# Synthetic Source\n")
    service = FieldService(registry)
    proposal = registration_plan(service, root, field_root=".", existing_source=False)
    return register_source(service, root, field_root=".", existing_source=False,
                           approved_digest=proposal.payload["approved_digest"])


def _files(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def pair(tmp_path):
    registry = KnowledgeSourceRegistry(tmp_path / "state/hub/sources.json")
    first_root = tmp_path / "source-a"
    first = _register_source(first_root, registry)
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"%PDF-1.7 synthetic ownership fixture\n")
    zotero = LocalZotero(pdf)
    first_selection = {"source_id": first.source_id, "field_id": first.fields[0].field_id,
                       "item_key": "ABCD2345", "attachment_key": "EFGH2345",
                       "segment": "original", "language": "en"}
    proposal = paper_plan(registry, zotero, **first_selection)
    register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **first_selection)
    second_root = tmp_path / "source-b"
    second = _register_source(second_root, registry)
    selection = dict(first_selection, source_id=second.source_id,
                     field_id=second.fields[0].field_id, segment="new-owner")
    providers = registry.path.parent / "knowledge-providers"
    second_snapshot = providers / second.source_id / "knowledge-provider.snapshot.json"
    second_snapshot_before = second_snapshot.read_bytes()
    assert json.loads(second_snapshot_before)["manifest"]["atomic_resources"] == []
    return SimpleNamespace(registry=registry, zotero=zotero, first=first, first_root=first_root,
                           second_root=second_root, selection=selection,
                           first_provider=providers / first.source_id / "knowledge-provider.snapshot.json",
                           second_provider=providers / second.source_id,
                           second_snapshot=second_snapshot, second_snapshot_before=second_snapshot_before)


def _replace_provider(pair, change):
    data = json.loads(pair.first_provider.read_text())
    change(data)
    data["snapshot_revision"] = ""
    data["catalog"]["revision"] = ""
    snapshot = KnowledgeProviderSnapshot.model_validate(data)
    pair.first_provider.write_text(snapshot.model_dump_json(indent=2) + "\n")


def _legacy_identity(data):
    data["catalog"]["resources"][0]["resource_id"] = "paper:legacy-owner"
    data["manifest"]["atomic_resources"][0]["resource_id"] = "paper:legacy-owner"
    # Model an imported legacy declaration, not a forged registration receipt.
    data["receipts"] = []


def _change_title(data):
    data["manifest"]["atomic_resources"][0]["title"] = "Outside declaration changed"


def test_another_registered_source_already_owns_the_paper(pair):
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="already has.*owner|duplicate"):
        paper_plan(pair.registry, pair.zotero, **pair.selection)
    assert _files(pair.second_root) == before
    assert pair.second_snapshot.read_bytes() == pair.second_snapshot_before


def test_legacy_matching_key_does_not_guess_library_identity(pair):
    _replace_provider(pair, _legacy_identity)
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="cannot be verified|unverifiable|library"):
        paper_plan(pair.registry, pair.zotero, **pair.selection)
    assert _files(pair.second_root) == before


def test_canonical_id_and_item_key_disagreement_is_unverifiable(pair):
    def contradict(data):
        data["catalog"]["resources"][0]["zotero"]["item_key"] = "JKLM2345"
        data["receipts"] = []

    _replace_provider(pair, contradict)
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="cannot be verified|unverifiable|identity"):
        paper_plan(pair.registry, pair.zotero, **pair.selection)
    assert _files(pair.second_root) == before


def test_same_key_in_another_proven_library_is_not_a_duplicate(pair):
    before = _files(pair.second_root)
    proposal = paper_plan(pair.registry, LocalZotero(pair.zotero.pdf, 456), **pair.selection)
    assert proposal["resource_id"] == "paper:zotero:456:ABCD2345"
    assert proposal["owner_path"] == "resources/papers/new-owner/Paper.md"
    assert _files(pair.second_root) == before
    assert pair.second_snapshot.read_bytes() == pair.second_snapshot_before


def test_same_key_in_another_library_inside_one_source_is_allowed(tmp_path):
    registry = KnowledgeSourceRegistry(tmp_path / "state/hub/sources.json")
    root = tmp_path / "single-source"
    manifest = _register_source(root, registry)
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"%PDF-1.7 synthetic ownership fixture\n")
    selection = {"source_id": manifest.source_id, "field_id": manifest.fields[0].field_id,
                 "item_key": "ABCD2345", "attachment_key": "EFGH2345",
                 "segment": "original", "language": "en"}
    first_zotero = LocalZotero(pdf, 123)
    first = paper_plan(registry, first_zotero, **selection)
    register_paper(registry, first_zotero, approved_digest=first["approved_digest"], **selection)
    before = _files(root)
    proposal = paper_plan(registry, LocalZotero(pdf, 456), **dict(selection, segment="other-library"))
    assert proposal["resource_id"] == "paper:zotero:456:ABCD2345"
    assert proposal["owner_path"] == "resources/papers/other-library/Paper.md"
    assert _files(root) == before


@pytest.mark.parametrize("condition", ["missing", "invalid", "symlink", "fifo", "disabled", "root"])
def test_unavailable_outside_source_cannot_prove_uniqueness(pair, tmp_path, condition):
    if condition in {"missing", "symlink", "fifo"}:
        preserved = tmp_path / "preserved-provider.json"
        pair.first_provider.rename(preserved)
        if condition == "symlink":
            pair.first_provider.symlink_to(preserved)
        elif condition == "fifo":
            os.mkfifo(pair.first_provider)
    elif condition == "invalid":
        pair.first_provider.write_text('{"invalid":')
    elif condition == "disabled":
        document = pair.registry.load_document()
        next(row for row in document.sources if row.source_id == pair.first.source_id).enabled = False
        pair.registry.save(document)
    else:
        pair.first_root.rename(tmp_path / "preserved-source-a")
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="cannot be verified|unavailable|declaration|disabled"):
        paper_plan(pair.registry, LocalZotero(pair.zotero.pdf, 456), **pair.selection)
    assert _files(pair.second_root) == before
    assert pair.second_snapshot.read_bytes() == pair.second_snapshot_before


def test_outside_declaration_change_invalidates_preview(pair):
    # Different libraries allow a valid preview; changing A must still invalidate it.
    zotero = LocalZotero(pair.zotero.pdf, 456)
    proposal = paper_plan(pair.registry, zotero, **pair.selection)
    _replace_provider(pair, _change_title)
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="plan changed|ownership declarations changed"):
        register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"], **pair.selection)
    assert _files(pair.second_root) == before
    assert pair.second_snapshot.read_bytes() == pair.second_snapshot_before


def test_recovery_rechecks_outside_declarations(pair):
    zotero = LocalZotero(pair.zotero.pdf, 456)
    proposal = paper_plan(pair.registry, zotero, **pair.selection)

    def stop(phase):
        if phase == "member-1":
            raise RuntimeError("synthetic interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"],
                       fault_inject=stop, **pair.selection)
    _replace_provider(pair, _change_title)
    before = _files(pair.second_root)
    journal_files = _files(pair.second_provider)
    with pytest.raises(FieldRegistryError, match="ownership declarations changed|authority.*changed"):
        register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"], **pair.selection)
    assert _files(pair.second_root) == before
    assert _files(pair.second_provider) == journal_files


def test_unchanged_outside_declarations_allow_safe_recovery(pair):
    zotero = LocalZotero(pair.zotero.pdf, 456)
    proposal = paper_plan(pair.registry, zotero, **pair.selection)

    def stop(phase):
        if phase == "member-1":
            raise RuntimeError("synthetic interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"],
                       fault_inject=stop, **pair.selection)
    result = register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"],
                            **pair.selection)
    assert result["status"] == "registered"
    assert result["owner_path"] == "resources/papers/new-owner/Paper.md"
    assert result["resource_id"] == "paper:zotero:456:ABCD2345"
    assert (pair.second_root / "resources/papers/new-owner/Paper.md").is_file()


def test_human_edit_of_partial_note_is_preserved(pair):
    zotero = LocalZotero(pair.zotero.pdf, 456)
    proposal = paper_plan(pair.registry, zotero, **pair.selection)

    def stop(phase):
        if phase == "member-1":
            raise RuntimeError("synthetic interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"],
                       fault_inject=stop, **pair.selection)
    note = pair.second_root / "resources/papers/new-owner/Paper.md"
    note.write_text("# Human edit must remain\n")
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="conflict"):
        register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"], **pair.selection)
    assert _files(pair.second_root) == before
    assert note.read_text() == "# Human edit must remain\n"


def test_outside_change_stops_before_the_next_publication_member(pair):
    zotero = LocalZotero(pair.zotero.pdf, 456)
    proposal = paper_plan(pair.registry, zotero, **pair.selection)
    fields = pair.second_root / ".scholar-workflow/fields.yml"
    assert proposal["owner_path"] == "resources/papers/new-owner/Paper.md"
    fields_before = fields.read_bytes()

    def change(phase):
        if phase == "member-1":
            _replace_provider(pair, _change_title)

    with pytest.raises(FieldRegistryError, match="ownership declarations changed|authority.*changed"):
        register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"],
                       fault_inject=change, **pair.selection)
    assert fields.read_bytes() == fields_before
    assert pair.second_snapshot.read_bytes() == pair.second_snapshot_before
    assert (pair.second_root / proposal["owner_path"]).read_text() == proposal["note"]
    journal = pair.second_provider / f"paper-registration-{proposal['approved_digest']}.json"
    assert json.loads(journal.read_text())["status"] == "prepared"


def test_canonical_paper_identity_with_wrong_kind_is_not_free(pair):
    def contradict_kind(data):
        data["catalog"]["resources"][0]["kind"] = "technical_document"
        data["manifest"]["atomic_resources"][0]["kind"] = "technical_document"
        data["receipts"] = []

    _replace_provider(pair, contradict_kind)
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="identity|owner|duplicate|kind"):
        paper_plan(pair.registry, pair.zotero, **pair.selection)
    assert _files(pair.second_root) == before


def test_leading_zero_library_identity_is_refused(pair):
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="identity|library"):
        paper_plan(pair.registry, LocalZotero(pair.zotero.pdf, "0123"), **pair.selection)
    assert _files(pair.second_root) == before


def test_completed_replay_with_unchanged_declarations(pair):
    zotero = LocalZotero(pair.zotero.pdf, 456)
    proposal = paper_plan(pair.registry, zotero, **pair.selection)
    result = register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"],
                            **pair.selection)
    before = _files(pair.second_root)
    assert register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"],
                          **pair.selection) == result
    assert _files(pair.second_root) == before


def test_completed_replay_rechecks_outside_declarations(pair):
    zotero = LocalZotero(pair.zotero.pdf, 456)
    proposal = paper_plan(pair.registry, zotero, **pair.selection)
    register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"], **pair.selection)
    _replace_provider(pair, _change_title)
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="ownership declarations changed"):
        register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"], **pair.selection)
    assert _files(pair.second_root) == before


def test_completed_replay_rechecks_target_source_duplicate(pair):
    zotero = LocalZotero(pair.zotero.pdf, 456)
    proposal = paper_plan(pair.registry, zotero, **pair.selection)
    register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"], **pair.selection)
    provider = pair.second_provider / "knowledge-provider.snapshot.json"
    data = json.loads(provider.read_text())
    previous_revision = data["catalog"]["revision"]
    legacy = dict(data["catalog"]["resources"][0], resource_id="paper:legacy-second-owner")
    data["catalog"]["resources"].append(legacy)
    owner = dict(data["manifest"]["atomic_resources"][0], resource_id=legacy["resource_id"],
                 markdown_path="resources/papers/legacy/Paper.md")
    data["manifest"]["atomic_resources"].append(owner)
    data["catalog"]["revision"] = ""
    data["catalog"] = HubCatalog.model_validate(data["catalog"]).model_dump(mode="json")
    # A valid synthetic import follows the original receipt; do not erase it to
    # make replay fail on the unrelated missing-receipt check.
    semantic = {"change_id": "change:" + "1" * 64,
                "change_fingerprint": "sha256:" + "1" * 64,
                "source_receipt": "synthetic:legacy-import",
                "before_catalog_revision": previous_revision,
                "after_catalog_revision": data["catalog"]["revision"], "applied_artifact_ids": []}
    receipt = KnowledgeApplyReceipt(
        receipt_id="knowledge-apply:" + _hash_payload(semantic).removeprefix("sha256:"),
        applied_at=datetime(2026, 1, 1, tzinfo=UTC), **semantic,
    )
    data["receipts"].append(receipt.model_dump(mode="json"))
    data["snapshot_revision"] = ""
    snapshot = KnowledgeProviderSnapshot.model_validate(data)
    assert len(snapshot.receipts) == 2
    provider.write_text(snapshot.model_dump_json(indent=2) + "\n")
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="identity|owner|duplicate|library"):
        register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"], **pair.selection)
    assert _files(pair.second_root) == before


@pytest.mark.parametrize("change", ["provider-file", "fields-file", "fields-comment",
                                    "source-directory", "provider-directory", "registry-set"])
def test_outside_identity_or_registry_set_change_invalidates_approval(pair, tmp_path, change):
    zotero = LocalZotero(pair.zotero.pdf, 456)
    proposal = paper_plan(pair.registry, zotero, **pair.selection)
    fields = pair.first_root / ".scholar-workflow/fields.yml"
    if change in {"provider-file", "fields-file"}:
        target = pair.first_provider if change == "provider-file" else fields
        original = target.read_bytes()
        target.rename(tmp_path / "preserved-declaration")
        target.write_bytes(original)
    elif change == "fields-comment":
        fields.write_text(fields.read_text() + "\n# Outside edit\n")
    elif change in {"source-directory", "provider-directory"}:
        target = pair.first_root if change == "source-directory" else pair.first_provider.parent
        saved = tmp_path / "preserved-directory"
        target.rename(saved)
        shutil.copytree(saved, target)
    else:
        _register_source(tmp_path / "source-c", pair.registry)
    before = _files(pair.second_root)
    with pytest.raises(FieldRegistryError, match="changed|cannot be verified"):
        register_paper(pair.registry, zotero, approved_digest=proposal["approved_digest"], **pair.selection)
    assert _files(pair.second_root) == before
    assert pair.second_snapshot.read_bytes() == pair.second_snapshot_before


def test_provider_lock_order_is_sorted_and_each_source_is_locked_once(pair, monkeypatch):
    from scholar_workflow.workflows import register_paper as workflow

    acquired = []
    original = workflow._locked_state_root

    @contextmanager
    def observe(path):
        acquired.append(path.name)
        with original(path) as state:
            yield state

    monkeypatch.setattr(workflow, "_locked_state_root", observe)
    assert pair.second_snapshot.read_bytes() == pair.second_snapshot_before
    with pair.registry._write_guard(), workflow._locked_registered_providers(
        pair.registry, pair.selection["source_id"],
    ):
        assert acquired == sorted([pair.first.source_id, pair.selection["source_id"]])
