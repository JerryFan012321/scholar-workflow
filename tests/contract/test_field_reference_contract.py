"""Independent portable Field-reference syntax and metadata replay contract."""
# ruff: noqa: F811 - explicitly imported pytest fixture injection
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from scholar_workflow.knowledge.fields import FieldManifest, FieldRegistryError, FieldService
from scholar_workflow.workflows.knowledge_reproduction import _load_package, reproduction_plan
from tests.contract.test_canvas_registration import canvas_scope  # noqa: F401
from tests.contract.test_paper_registration import scope  # noqa: F401

_SOURCE = "11111111-1111-4111-8111-111111111111"
_FIELD = "22222222-2222-4222-8222-222222222222"
_EXTERNAL_SOURCE = "abcdefab-cdef-4abc-8def-abcdefabcdef"
_TARGET = "paper:zotero:123:JKLM2345"


def _reference() -> dict:
    return {"reference_id": "ref:external-paper",
            "target": {"source_id": _EXTERNAL_SOURCE, "object_id": _TARGET},
            "purpose": "Compare this existing paper in the selected research context."}


def _manifest(version: int = 1) -> dict:
    value = {"schema_version": version, "source_id": _SOURCE, "fields": [{
        "field_id": _FIELD, "title": "Synthetic topic", "relative_root": "topic",
        "home": "README.md", "navigation": [{"label": "Existing notes", "items": ["Notes.md"]}],
    }]}
    if version == 2:
        value["fields"][0]["references"] = [_reference()]
    return value


def _files(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file() and not path.is_symlink()}


def _field_json_validator():
    contracts = Path(__file__).resolve().parents[2] / "contracts"
    package_schema = json.loads((contracts / "knowledge-reproduction-package.schema.json").read_bytes())
    return jsonschema.Draft202012Validator({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/FieldManifest", "$defs": package_schema["$defs"],
    })


def test_schema_one_retains_exact_old_dictionary_and_json_shape():
    expected = _manifest()
    model = FieldManifest.model_validate(copy.deepcopy(expected))
    assert model.model_dump(mode="json") == expected
    assert json.loads(model.model_dump_json()) == expected
    loaded = FieldManifest.model_validate_json(json.dumps(expected))
    assert loaded.model_dump(mode="json") == expected
    assert "references" not in loaded.model_dump(mode="json")["fields"][0]


@pytest.mark.parametrize("references", [[], [_reference()]])
def test_schema_one_rejects_even_explicit_empty_references(references):
    value = _manifest()
    value["fields"][0]["references"] = references
    with pytest.raises(ValueError):
        FieldManifest.model_validate(value)


def test_schema_two_preserves_qualified_reference_without_changing_navigation():
    expected = _manifest(2)
    original_navigation = copy.deepcopy(expected["fields"][0]["navigation"])
    model = FieldManifest.model_validate(copy.deepcopy(expected))
    assert model.model_dump(mode="json") == expected
    assert json.loads(model.model_dump_json()) == expected
    assert model.model_dump(mode="json")["fields"][0]["navigation"] == original_navigation
    assert model.model_dump(mode="json")["fields"][0]["home"] == "README.md"


@pytest.mark.parametrize("duplicate", ["reference_id", "qualified_target"])
def test_one_field_rejects_duplicate_reference_id_or_qualified_target(duplicate):
    value = _manifest(2)
    second = _reference()
    if duplicate == "reference_id":
        second["target"]["object_id"] = "paper:zotero:123:NPQR2345"
    else:
        second["reference_id"] = "ref:second-context"
    value["fields"][0]["references"].append(second)
    with pytest.raises(ValueError):
        FieldManifest.model_validate(value)


def test_same_object_in_distinct_sources_is_structurally_distinct():
    value = _manifest(2)
    second = _reference()
    second["reference_id"] = "ref:another-source"
    second["target"]["source_id"] = "33333333-3333-4333-8333-333333333333"
    value["fields"][0]["references"].append(second)
    assert FieldManifest.model_validate(value).model_dump(mode="json") == value


def test_reference_ids_and_targets_are_local_to_each_field():
    value = _manifest(2)
    second = copy.deepcopy(value["fields"][0])
    second.update(field_id="44444444-4444-4444-8444-444444444444", relative_root="another-topic")
    value["fields"].append(second)
    assert FieldManifest.model_validate(value).model_dump(mode="json") == value


@pytest.mark.parametrize("version", [0, 3, -1, True, "2", None])
def test_unknown_or_noninteger_schema_version_refuses(version):
    value = _manifest()
    value["schema_version"] = version
    with pytest.raises(ValueError):
        FieldManifest.model_validate(value)


@pytest.mark.parametrize("reference_id", ["", "a", "Ref:paper", " ref:paper", "a/b", "a" * 129])
def test_reference_id_must_be_a_bounded_portable_identifier(reference_id):
    value = _manifest(2)
    value["fields"][0]["references"][0]["reference_id"] = reference_id
    with pytest.raises(ValueError):
        FieldManifest.model_validate(value)


@pytest.mark.parametrize("object_id", ["", "/tmp/paper.md", "../Paper.md", "a/b",
                                       "obsidian://open", "https://example.invalid/paper",
                                       " paper:one", "a" * 257])
def test_object_id_is_stable_identity_not_a_path_or_url(object_id):
    value = _manifest(2)
    value["fields"][0]["references"][0]["target"]["object_id"] = object_id
    with pytest.raises(ValueError):
        FieldManifest.model_validate(value)


@pytest.mark.parametrize("source_id", ["invalid", _EXTERNAL_SOURCE.upper(),
                                       _EXTERNAL_SOURCE.replace("-", ""), "/tmp/source"])
def test_target_source_id_requires_canonical_uuid(source_id):
    value = _manifest(2)
    value["fields"][0]["references"][0]["target"]["source_id"] = source_id
    with pytest.raises(ValueError):
        FieldManifest.model_validate(value)


@pytest.mark.parametrize("purpose", [None, "", " ", " surrounded ", "line\nbreak", "bad\x00text", "x" * 2001])
def test_reference_requires_clean_nonempty_bounded_purpose(purpose):
    value = _manifest(2)
    value["fields"][0]["references"][0]["purpose"] = purpose
    with pytest.raises(ValueError):
        FieldManifest.model_validate(value)


def test_reference_without_purpose_refuses():
    value = _manifest(2)
    del value["fields"][0]["references"][0]["purpose"]
    with pytest.raises(ValueError):
        FieldManifest.model_validate(value)


@pytest.mark.parametrize("level,key", [("reference", "path"), ("reference", "url"),
                                      ("target", "path"), ("target", "url"),
                                      ("field", "path"), ("field", "url")])
def test_extra_path_or_url_fields_refuse(level, key):
    value = _manifest(2)
    field = value["fields"][0]
    reference = field["references"][0]
    destination = {"field": field, "reference": reference, "target": reference["target"]}[level]
    destination[key] = "/tmp/outside.md" if key == "path" else "https://example.invalid/paper"
    with pytest.raises(ValueError):
        FieldManifest.model_validate(value)


def test_reference_field_length_upper_bounds_accept():
    value = _manifest(2)
    reference = value["fields"][0]["references"][0]
    reference.update(reference_id="a" * 128, purpose="x" * 2000)
    reference["target"]["object_id"] = "a" * 256
    assert FieldManifest.model_validate(value).model_dump(mode="json") == value


@pytest.mark.parametrize("count,accepted", [(512, True), (513, False)])
def test_reference_count_is_bounded_per_field(count, accepted):
    value = _manifest(2)
    value["fields"][0]["references"] = [{
        "reference_id": f"ref:{index}",
        "target": {"source_id": _EXTERNAL_SOURCE, "object_id": f"document:{index}"},
        "purpose": "Explicit synthetic context.",
    } for index in range(count)]
    if accepted:
        assert FieldManifest.model_validate(value).model_dump(mode="json") == value
    else:
        with pytest.raises(ValueError):
            FieldManifest.model_validate(value)


@pytest.mark.parametrize("case,accepted", [("schema-one", True), ("schema-two", True),
                                          ("schema-one-references", False),
                                          ("schema-three", False), ("target-url", False)])
def test_public_reproduction_json_mapping_tracks_both_field_versions(case, accepted):
    value = _manifest(1 if case.startswith("schema-one") else 2)
    if case == "schema-one-references":
        value["fields"][0]["references"] = []
    elif case == "schema-three":
        value["schema_version"] = 3
    elif case == "target-url":
        value["fields"][0]["references"][0]["target"]["url"] = "https://example.invalid"
    validator = _field_json_validator()
    if accepted:
        validator.validate(value)
    else:
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(value)


@pytest.mark.parametrize("schema_mode", ["validation", "serialization"])
@pytest.mark.parametrize("case,accepted", [
    ("schema-one", True), ("schema-two", True),
    ("schema-one-empty-references", False), ("schema-one-references", False),
    ("schema-three", False), ("schema-boolean", False), ("schema-string", False),
    ("reference-uppercase", False), ("reference-path", False),
    ("target-path", False), ("target-url", False),
    ("source-uppercase", False), ("source-invalid", False),
])
def test_dynamic_field_json_schema_tracks_version_and_reference_identity(schema_mode, case, accepted):
    value = _manifest(1 if case.startswith("schema-one") else 2)
    if case == "schema-one-empty-references":
        value["fields"][0]["references"] = []
    elif case == "schema-one-references":
        value["fields"][0]["references"] = [_reference()]
    elif case.startswith("schema-") and case not in {"schema-one", "schema-two"}:
        value["schema_version"] = {"schema-three": 3, "schema-boolean": True, "schema-string": "2"}[case]
    elif case.startswith("reference-"):
        value["fields"][0]["references"][0]["reference_id"] = (
            "Ref:paper" if case == "reference-uppercase" else "notes/Paper.md"
        )
    elif case.startswith("target-"):
        value["fields"][0]["references"][0]["target"]["object_id"] = (
            "/outside/Paper.md" if case == "target-path" else "https://example.invalid/paper"
        )
    elif case.startswith("source-"):
        value["fields"][0]["references"][0]["target"]["source_id"] = (
            _EXTERNAL_SOURCE.upper() if case == "source-uppercase" else "not-a-uuid"
        )
    validator = jsonschema.Draft202012Validator(FieldManifest.model_json_schema(mode=schema_mode))
    if accepted:
        validator.validate(value)
    else:
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(value)


@pytest.mark.parametrize("schema_kind", ["static", "validation", "serialization"])
@pytest.mark.parametrize("purpose", ["\x00", "a\x00", "\x00a", " a", "a ", "a\nb"])
def test_field_reference_json_schemas_reject_dirty_purpose_endpoints(schema_kind, purpose):
    value = _manifest(2)
    value["fields"][0]["references"][0]["purpose"] = purpose
    validator = (
        _field_json_validator() if schema_kind == "static" else
        jsonschema.Draft202012Validator(FieldManifest.model_json_schema(mode=schema_kind))
    )
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(value)


def _manifest_with_reference_trailing_newline(member: str) -> dict:
    value = _manifest(2)
    reference = value["fields"][0]["references"][0]
    destination = reference if member in {"purpose", "reference_id"} else reference["target"]
    destination[member] += "\n"
    return value


@pytest.mark.parametrize("schema_kind", ["static", "validation", "serialization"])
@pytest.mark.parametrize("member", ["purpose", "reference_id", "object_id", "source_id"])
def test_field_reference_json_schemas_reject_trailing_newline(schema_kind, member):
    value = _manifest_with_reference_trailing_newline(member)
    validator = (
        _field_json_validator() if schema_kind == "static" else
        jsonschema.Draft202012Validator(FieldManifest.model_json_schema(mode=schema_kind))
    )
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(value)


@pytest.mark.parametrize("member", ["purpose", "reference_id", "object_id", "source_id"])
def test_field_reference_python_model_rejects_trailing_newline(member):
    with pytest.raises(ValueError):
        FieldManifest.model_validate(_manifest_with_reference_trailing_newline(member))


def test_schema_two_reference_metadata_survives_whole_package_roundtrip(canvas_scope, tmp_path):
    root, registry, selection, _, provider = canvas_scope
    fields_path = root / ".scholar-workflow/fields.yml"
    expected = yaml.safe_load(fields_path.read_bytes())
    original_navigation = copy.deepcopy(expected["fields"][0]["navigation"])
    expected["schema_version"] = 2
    expected["fields"][0]["references"] = [_reference()]
    fields_path.write_text(yaml.safe_dump(expected, sort_keys=False))
    external = tmp_path / "external-owned-body.md"
    external.write_bytes(b"Synthetic external body: never copy or adopt.\n")
    source_before, state_before = _files(root), _files(registry.path.parent)
    plan = reproduction_plan(registry, source_id=selection["source_id"])
    package = json.loads(json.dumps(plan["package"]))
    assert package["fields"] == expected
    assert package["fields"]["fields"][0]["navigation"] == original_navigation
    assert package["files"][".scholar-workflow/fields.yml"] == (
        "sha256:" + hashlib.sha256(fields_path.read_bytes()).hexdigest()
    )
    assert _TARGET not in {row["resource_id"] for row in package["provider"]["manifest"]["atomic_resources"]}
    assert _TARGET not in {row["resource_id"] for row in package["provider"]["catalog"]["resources"]}
    assert external.name not in package["files"]
    assert not (root / external.name).exists()
    replay_input = tmp_path / "portable-reference-package.json"
    replay_input.write_text(json.dumps(package))
    loaded, fields, _, _ = _load_package(replay_input)
    assert loaded == package
    assert fields.model_dump(mode="json") == expected
    assert _files(root) == source_before
    assert _files(registry.path.parent) == state_before
    assert provider.is_dir()


def test_references_do_not_expand_local_document_authorization(canvas_scope):
    root, registry, selection, _, _ = canvas_scope
    fields_path = root / ".scholar-workflow/fields.yml"
    value = yaml.safe_load(fields_path.read_bytes())
    navigation = copy.deepcopy(value["fields"][0]["navigation"])
    value["schema_version"] = 2
    value["fields"][0]["references"] = [_reference()]
    fields_path.write_text(yaml.safe_dump(value, sort_keys=False))
    unlisted = root / "Borrowed.md"
    unlisted.write_bytes(b"# An existing but undeclared local file\n")
    before, state = _files(root), _files(registry.path.parent)
    service = FieldService(registry)
    assert service.read_document(selection["field_id"], "README.md")["content"] == (
        root / "README.md"
    ).read_text()
    with pytest.raises(FieldRegistryError):
        service.read_document(selection["field_id"], "Borrowed.md")
    with pytest.raises(FieldRegistryError):
        service.write_document(selection["field_id"], "Borrowed.md", content="Overwrite refused\n",
                               base_revision="sha256:" + hashlib.sha256(unlisted.read_bytes()).hexdigest())
    assert yaml.safe_load(fields_path.read_bytes())["fields"][0]["navigation"] == navigation
    assert _files(root) == before
    assert _files(registry.path.parent) == state
