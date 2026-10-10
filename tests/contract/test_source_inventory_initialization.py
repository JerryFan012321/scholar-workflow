"""Independent expectations for recoverable new-Source empty inventories.

Prepared before the feature. Do not use production validation/locking helpers as
the expected-result oracle. All filesystem and Local API inputs are synthetic.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow.analysis.apply_changes import KnowledgeApplySafetyError
from scholar_workflow.cli import main
from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)
from scholar_workflow.knowledge.registration import registration_plan
from scholar_workflow.workflows.register_paper import paper_plan, register_paper

_SNAPSHOT = "knowledge-provider.snapshot.json"
_PHASES = ("provider-created", "manifest-published", "registry-published")
_PROSE = {"README.md": b"# Existing readable home\n",
          "Reading.md": b"# Preserve this human note\n\nExisting prose.\n"}


def _root(tmp_path: Path, name: str = "source") -> Path:
    root = tmp_path.resolve() / name
    root.mkdir()
    for filename, content in _PROSE.items():
        (root / filename).write_bytes(content)
    return root


def _service(tmp_path: Path) -> FieldService:
    return FieldService(KnowledgeSourceRegistry(tmp_path / "state/hub/sources.json"))


def _state(service: FieldService) -> Path:
    return service.registry.path.parent.parent


def _files(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file() and not path.is_symlink()}


def _prose_unchanged(root: Path) -> None:
    assert {name: (root / name).read_bytes() for name in _PROSE} == _PROSE


def _plan(service: FieldService, root: Path, *, existing: bool = False) -> dict:
    return registration_plan(service, root, field_root=None if existing else ".",
                             existing_source=existing).payload


def _register(service: FieldService, root: Path, digest: str, *,
              existing: bool = False, fault=None):
    # Import at call time: the absent entry point is a feature RED, not a
    # collection failure for other contract tests.
    from scholar_workflow.workflows.register_source import register_source

    return register_source(service, root, field_root=None if existing else ".",
                           existing_source=existing, approved_digest=digest,
                           fault_inject=fault)


def _snapshot(service: FieldService, source_id: str) -> Path:
    return service.registry.path.parent / "knowledge-providers" / source_id / _SNAPSHOT


def _empty_snapshot(path: Path, root: Path) -> dict:
    value = json.loads(path.read_bytes())
    info = root.stat()
    assert value["vault_binding"] == {
        "root_path": str(root.resolve()), "device": info.st_dev, "inode": info.st_ino,
    }
    for key in ("atomic_resources", "core_documents", "supporting_documents"):
        assert value["manifest"][key] == []
    for key in ("artifacts", "relations", "projections"):
        assert value[key] == []
    for key in ("resources", "topics", "artifacts", "assets"):
        assert value["catalog"][key] == []
    return value


def _initialize(service: FieldService, root: Path):
    proposal = _plan(service, root)
    assert proposal["inventory_initialization"] == "new-empty-provider"
    manifest = _register(service, root, proposal["approved_digest"])
    _empty_snapshot(_snapshot(service, manifest.source_id), root)
    _prose_unchanged(root)
    return manifest


def _journal(service: FieldService) -> Path:
    # Recovery state may use a dedicated directory; this test does not invent
    # a new storage layout or treat journals as another owner authority.
    records = [path for path in _state(service).rglob("*.json")
               if path.name not in {_SNAPSHOT, service.registry.path.name}]
    assert len(records) == 1
    return records[0]


def _interrupt(service: FieldService, root: Path, phase: str) -> dict:
    proposal = _plan(service, root)
    seen = []

    def stop(observed: str) -> None:
        seen.append(observed)
        if observed == phase:
            raise RuntimeError("Synthetic Source-creation interruption")

    with pytest.raises(RuntimeError, match="Synthetic Source-creation interruption"):
        _register(service, root, proposal["approved_digest"], fault=stop)
    assert phase in seen
    _prose_unchanged(root)
    return proposal


class _LocalPaper:
    def __init__(self, pdf: Path, item: str = "ABCD2345", attachment: str = "EFGH2345"):
        self.pdf = pdf
        self.item = item
        self.attachment = attachment

    def get_item(self, key: str) -> dict:
        assert key in {self.item, self.attachment}
        data = ({"itemType": "preprint", "title": "Synthetic paper " + self.item}
                if key == self.item else
                {"itemType": "attachment", "parentItem": self.item,
                 "contentType": "application/pdf", "linkMode": "imported_file"})
        return {"key": key, "library": {"id": 123, "type": "user"}, "data": data}

    def resolve_attachment_locator(self, key: str):
        assert key == self.attachment
        return SimpleNamespace(path=self.pdf, attachment_key=key, library_id="123")


def _paper(tmp_path: Path, item: str = "ABCD2345", attachment: str = "EFGH2345"):
    pdf = tmp_path / (item + ".pdf")
    pdf.write_bytes(b"%PDF-1.7 synthetic locator bytes, not a real paper\n")
    return _LocalPaper(pdf, item, attachment)


def _selection(manifest, paper: _LocalPaper, segment: str = "synthetic-paper") -> dict:
    return {"source_id": manifest.source_id, "field_id": manifest.fields[0].field_id,
            "item_key": paper.item, "attachment_key": paper.attachment,
            "segment": segment, "language": "en"}


def _historical(tmp_path: Path, service: FieldService):
    """Hand-written old declarations: missing provider has unknown history."""
    root = _root(tmp_path, "historical")
    source_id = "11111111-1111-4111-8111-111111111111"
    field_id = "22222222-2222-4222-8222-222222222222"
    portable = {"schema_version": 1, "source_id": source_id, "fields": [{
        "field_id": field_id, "title": "Historical Field", "relative_root": ".",
        "home": "README.md", "navigation": [],
    }]}
    (root / ".scholar-workflow").mkdir()
    (root / ".scholar-workflow/fields.yml").write_text(yaml.safe_dump(portable))
    registry = service.registry.path
    document = (json.loads(registry.read_bytes()) if registry.exists() else
                {"schema_version": 1, "folders": [], "sources": []})
    document["folders"].append({"folder_id": "historical-source", "root": str(root),
                                "enabled": True, "capabilities": ["read", "write"]})
    document["sources"].append({"source_id": source_id, "provider": "obsidian",
                                "folder_id": "historical-source", "enabled": True,
                                "capabilities": ["read", "write"]})
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps(document))
    return root, source_id, field_id


def test_public_plan_explicitly_binds_new_empty_inventory_without_writes(tmp_path):
    root, service = _root(tmp_path), _service(tmp_path)
    before = _files(tmp_path)
    runner = CliRunner()
    args = ["knowledge", "registration-plan", str(root), "--field-root", ".",
            "--format", "json"]
    env = {"SCHOLAR_WORKFLOW_HOME": str(_state(service))}
    first, second = [runner.invoke(main, args, env=env) for _ in range(2)]
    assert first.exit_code == second.exit_code == 0
    left, right = json.loads(first.output), json.loads(second.output)
    assert left["inventory_initialization"] == right["inventory_initialization"] == "new-empty-provider"
    assert left["approved_digest"] == right["approved_digest"]
    assert left["status"] == "ready-for-confirmation"
    assert _files(tmp_path) == before


def test_public_register_creates_bound_empty_provider_and_preserves_prose(tmp_path):
    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _plan(service, root)
    result = CliRunner().invoke(main, ["knowledge", "register", str(root), "--field-root", ".",
                                      "--approved-digest", proposal["approved_digest"],
                                      "--yes", "--format", "json"],
                                env={"SCHOLAR_WORKFLOW_HOME": str(_state(service))})
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["status"] == "registered"
    portable = yaml.safe_load((root / ".scholar-workflow/fields.yml").read_bytes())
    assert receipt["manifest"] == portable
    _empty_snapshot(_snapshot(service, portable["source_id"]), root)
    _prose_unchanged(root)


def test_old_digest_without_inventory_action_cannot_authorize_creation(tmp_path):
    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _plan(service, root)
    assert proposal["inventory_initialization"] == "new-empty-provider"
    reduced = {key: value for key, value in proposal.items()
               if key not in {"approved_digest", "inventory_initialization"}}
    old_digest = hashlib.sha256(json.dumps(reduced, sort_keys=True, ensure_ascii=False,
                                          separators=(",", ":")).encode()).hexdigest()
    assert old_digest != proposal["approved_digest"]
    before = _files(tmp_path)
    with pytest.raises(FieldRegistryError):
        _register(service, root, old_digest)
    assert _files(tmp_path) == before


def test_two_new_empty_sources_accept_different_papers(tmp_path):
    service = _service(tmp_path)
    roots = [_root(tmp_path, name) for name in ("one", "two")]
    manifests = [_initialize(service, root) for root in roots]
    assert manifests[0].source_id != manifests[1].source_id
    papers = [_paper(tmp_path), _paper(tmp_path, "JKLM2345", "NPQR2345")]
    for root, manifest, paper in zip(roots, manifests, papers, strict=True):
        selection = _selection(manifest, paper)
        proposal = paper_plan(service.registry, paper, **selection)
        register_paper(service.registry, paper, approved_digest=proposal["approved_digest"], **selection)
        snapshot = json.loads(_snapshot(service, manifest.source_id).read_bytes())
        assert [row["resource_id"] for row in snapshot["manifest"]["atomic_resources"]] == [
            "paper:zotero:123:" + paper.item,
        ]
        assert [row["zotero"]["item_key"] for row in snapshot["catalog"]["resources"]] == [paper.item]
        _prose_unchanged(root)


def test_same_library_and_item_cannot_acquire_second_source_owner(tmp_path):
    service = _service(tmp_path)
    roots = [_root(tmp_path, name) for name in ("one", "two")]
    first, second = [_initialize(service, root) for root in roots]
    paper = _paper(tmp_path)
    selection = _selection(first, paper)
    proposal = paper_plan(service.registry, paper, **selection)
    register_paper(service.registry, paper, approved_digest=proposal["approved_digest"], **selection)
    before = _files(tmp_path)
    with pytest.raises(FieldRegistryError):
        paper_plan(service.registry, paper, **_selection(second, paper, "duplicate"))
    assert _files(tmp_path) == before
    assert not (roots[1] / "resources/papers/duplicate").exists()


@pytest.mark.parametrize("missing_source", ["selected", "external"])
def test_historical_missing_provider_is_not_an_empty_inventory(tmp_path, missing_source):
    service = _service(tmp_path)
    if missing_source == "external":
        selected = _initialize(service, _root(tmp_path, "selected"))
    old_root, source_id, field_id = _historical(tmp_path, service)
    paper = _paper(tmp_path)
    selection = (_selection(selected, paper) if missing_source == "external" else
                 {"source_id": source_id, "field_id": field_id, "item_key": paper.item,
                  "attachment_key": paper.attachment, "segment": "must-refuse", "language": "en"})
    before = _files(tmp_path)
    with pytest.raises(FieldRegistryError):
        paper_plan(service.registry, paper, **selection)
    assert _files(tmp_path) == before
    assert not _snapshot(service, source_id).exists()
    assert not (old_root / "resources").exists()


def test_existing_source_attachment_never_initializes_empty_provider(tmp_path):
    source_service = _service(tmp_path)
    root, source_id, _ = _historical(tmp_path, source_service)
    other = FieldService(KnowledgeSourceRegistry(tmp_path / "other-state/hub/sources.json"))
    original = (root / ".scholar-workflow/fields.yml").read_bytes()
    proposal = _plan(other, root, existing=True)
    assert proposal["mode"] == "existing-source"
    assert proposal.get("inventory_initialization") is None
    manifest = _register(other, root, proposal["approved_digest"], existing=True)
    assert manifest.source_id == source_id
    assert (root / ".scholar-workflow/fields.yml").read_bytes() == original
    assert not _snapshot(other, source_id).exists()
    _prose_unchanged(root)


@pytest.mark.parametrize("phase", _PHASES)
def test_interrupted_creation_resumes_original_digest_and_frozen_ids(tmp_path, phase):
    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _interrupt(service, root, phase)
    snapshots = list(_state(service).rglob(_SNAPSHOT))
    assert len(snapshots) == 1
    source_id = snapshots[0].parent.name
    _empty_snapshot(snapshots[0], root)
    portable_path = root / ".scholar-workflow/fields.yml"
    assert portable_path.exists() == (phase != "provider-created")
    assert service.registry.path.exists() == (phase == "registry-published")
    frozen_field = (yaml.safe_load(portable_path.read_bytes())["fields"][0]["field_id"]
                    if portable_path.exists() else None)
    assert json.loads(_journal(service).read_bytes())["status"] == "prepared"
    # A fresh service loses all process-local preview tokens. Recovery must read
    # the original digest journal before attempting an ordinary new preview.
    fresh = FieldService(KnowledgeSourceRegistry(service.registry.path))
    manifest = _register(fresh, root, proposal["approved_digest"])
    assert manifest.source_id == source_id
    if frozen_field is not None:
        assert manifest.fields[0].field_id == frozen_field
    registry = json.loads(service.registry.path.read_bytes())
    assert [row["source_id"] for row in registry["sources"]] == [source_id]
    assert len(list(_state(service).rglob(_SNAPSHOT))) == 1
    assert json.loads(_journal(service).read_bytes())["status"] == "committed"
    complete = _files(tmp_path)
    replay = _register(fresh, root, proposal["approved_digest"])
    assert replay == manifest
    assert _files(tmp_path) == complete
    _prose_unchanged(root)


@pytest.mark.parametrize("member,phase", [
    ("provider", "provider-created"), ("manifest", "manifest-published"),
    ("registry", "registry-published"), ("prose", "manifest-published"),
])
def test_recovery_member_drift_refuses_and_preserves_current_bytes(tmp_path, member, phase):
    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _interrupt(service, root, phase)
    if member == "provider":
        path = next(_state(service).rglob(_SNAPSHOT))
        path.write_bytes(path.read_bytes() + b"\n")
    elif member == "manifest":
        path = root / ".scholar-workflow/fields.yml"
        path.write_bytes(path.read_bytes() + b"\n# Human changed the manifest\n")
    elif member == "registry":
        document = json.loads(service.registry.path.read_bytes())
        document["sources"][0]["enabled"] = False
        service.registry.path.write_text(json.dumps(document))
    else:
        (root / "README.md").write_bytes(b"# Human replacement: never overwrite\n")
    changed = _files(tmp_path)
    fresh = FieldService(KnowledgeSourceRegistry(service.registry.path))
    with pytest.raises(FieldRegistryError):
        _register(fresh, root, proposal["approved_digest"])
    assert _files(tmp_path) == changed


@pytest.mark.parametrize("damage", ["malformed", "root-substitution"])
def test_damaged_prepared_journal_refuses_without_publication(tmp_path, damage):
    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _interrupt(service, root, "provider-created")
    journal = _journal(service)
    if damage == "malformed":
        journal.write_bytes(b'{"status":"prepared", damaged')
    else:
        substituted = _root(tmp_path, "substituted")
        raw = journal.read_text()
        assert str(root) in raw
        journal.write_text(raw.replace(str(root), str(substituted)))
    changed = _files(tmp_path)
    fresh = FieldService(KnowledgeSourceRegistry(service.registry.path))
    with pytest.raises(FieldRegistryError):
        _register(fresh, root, proposal["approved_digest"])
    assert _files(tmp_path) == changed
    assert not (root / ".scholar-workflow/fields.yml").exists()


def test_committed_creation_cannot_recreate_a_lost_provider(tmp_path):
    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _plan(service, root)
    manifest = _register(service, root, proposal["approved_digest"])
    snapshot = _snapshot(service, manifest.source_id)
    assert snapshot.is_file()
    assert json.loads(_journal(service).read_bytes())["status"] == "committed"
    snapshot.unlink()
    damaged = _files(tmp_path)
    fresh = FieldService(KnowledgeSourceRegistry(service.registry.path))
    with pytest.raises(FieldRegistryError):
        _register(fresh, root, proposal["approved_digest"])
    assert not snapshot.exists()
    assert _files(tmp_path) == damaged


@pytest.mark.parametrize("member", ["fields", "registry", "provider"])
def test_recomputed_journal_checksum_does_not_approve_unrelated_members(tmp_path, monkeypatch, member):
    from scholar_workflow.workflows import register_source as workflow

    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _plan(service, root)
    create = workflow._atomic_create

    def stop_after_journal(fd, name, content):
        create(fd, name, content)
        if name.startswith("source-registration-"):
            raise RuntimeError("Synthetic durable journal interruption")

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "_atomic_create", stop_after_journal)
        with pytest.raises(RuntimeError, match="durable journal"):
            _register(service, root, proposal["approved_digest"])
    journal = _journal(service)
    value = json.loads(journal.read_bytes())
    creation = value["creation"]
    if member == "fields":
        fields = yaml.safe_load(creation["fields_after"])
        fields["fields"][0]["title"] = "Unapproved replacement"
        creation["fields_after"] = yaml.safe_dump(fields)
    elif member == "registry":
        registry = json.loads(creation["registry_after"])
        registry["folders"].append({"folder_id": "unapproved-extra", "root": str(tmp_path),
                                    "enabled": True, "capabilities": ["read", "write"]})
        creation["registry_after"] = json.dumps(registry)
    else:
        provider = json.loads(creation["provider_after"])
        provider["vault_binding"]["root_path"] = str(tmp_path)
        creation["provider_after"] = json.dumps(provider)
    encoded = (json.dumps(creation, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    value["fingerprint"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    journal.write_text(json.dumps(value))
    changed = _files(tmp_path)
    with pytest.raises(FieldRegistryError, match="journal|approved|creation"):
        _register(FieldService(KnowledgeSourceRegistry(service.registry.path)), root,
                  proposal["approved_digest"])
    assert _files(tmp_path) == changed
    assert not service.registry.path.exists()
    assert not (root / ".scholar-workflow/fields.yml").exists()
    assert not list(_state(service).rglob(_SNAPSHOT))


def test_registry_parent_swap_between_lock_and_workflow_refuses(tmp_path, monkeypatch):
    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _plan(service, root)
    guard = service.registry._write_guard
    observed = {}

    @contextmanager
    def swapped_guard():
        with guard() as fd:
            service.registry.path.parent.rename(tmp_path / "preserved-registry-parent")
            service.registry.path.parent.mkdir()
            observed.update(_files(tmp_path))
            yield fd

    monkeypatch.setattr(service.registry, "_write_guard", swapped_guard)
    with pytest.raises(FieldRegistryError, match="directory|authority|binding"):
        _register(service, root, proposal["approved_digest"])
    assert _files(tmp_path) == observed
    assert not list(tmp_path.rglob(_SNAPSHOT))
    assert not (root / ".scholar-workflow/fields.yml").exists()


def test_registry_parent_swap_after_provider_checkpoint_refuses(tmp_path):
    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _plan(service, root)
    changed = {}

    def swap(phase):
        if phase == "provider-created":
            service.registry.path.parent.rename(tmp_path / "preserved-registry-parent")
            service.registry.path.parent.mkdir()
            changed.update(_files(tmp_path))

    with pytest.raises((FieldRegistryError, KnowledgeApplySafetyError, OSError)):
        _register(service, root, proposal["approved_digest"], fault=swap)
    assert _files(tmp_path) == changed
    assert not service.registry.path.exists()
    assert not (root / ".scholar-workflow/fields.yml").exists()


@pytest.mark.parametrize("member", [_SNAPSHOT, "fields.yml", "sources.json"])
def test_durable_member_before_progress_checkpoint_resumes_once(tmp_path, monkeypatch, member):
    from scholar_workflow.workflows import register_source as workflow

    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _plan(service, root)
    put = workflow._put

    def stop_before_progress(fd, name, before, after):
        put(fd, name, before, after)
        if name == member:
            raise RuntimeError("Synthetic missing progress checkpoint")

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "_put", stop_before_progress)
        with pytest.raises(RuntimeError, match="missing progress checkpoint"):
            _register(service, root, proposal["approved_digest"])
    prepared = json.loads(_journal(service).read_bytes())
    source_id = prepared["creation"]["manifest"]["source_id"]
    field_id = prepared["creation"]["manifest"]["fields"][0]["field_id"]
    fresh = FieldService(KnowledgeSourceRegistry(service.registry.path))
    completed = _register(fresh, root, proposal["approved_digest"])
    assert completed.source_id == source_id
    assert completed.fields[0].field_id == field_id
    _empty_snapshot(_snapshot(service, source_id), root)
    assert len(json.loads(service.registry.path.read_bytes())["sources"]) == 1
    before = _files(tmp_path)
    assert _register(fresh, root, proposal["approved_digest"]) == completed
    assert _files(tmp_path) == before
    _prose_unchanged(root)


def test_public_registration_reports_provider_safety_refusal(tmp_path, monkeypatch):
    root, service = _root(tmp_path), _service(tmp_path)
    proposal = _plan(service, root)
    before = _files(tmp_path)

    def refuse(*args, **kwargs):
        raise KnowledgeApplySafetyError("Synthetic provider directory conflict")

    monkeypatch.setattr("scholar_workflow.workflows.register_source.register_source", refuse)
    result = CliRunner().invoke(
        main, ["knowledge", "register", str(root), "--field-root", ".",
               "--approved-digest", proposal["approved_digest"], "--yes"],
        env={"SCHOLAR_WORKFLOW_HOME": str(_state(service))},
    )
    assert result.exit_code == 7
    assert "Synthetic provider directory conflict" in result.output
    assert _files(tmp_path) == before
