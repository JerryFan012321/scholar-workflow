"""Synthetic native reader checks; no real registry, API or application is used."""

import hashlib
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from scholar_workflow.adapters import exploration_readers as module
from scholar_workflow.adapters.zotero_local import ZoteroAttachmentLocator, ZoteroLocalUnavailable

PARENT, PDF, ANN = "ABCD2345", "BCDE3456", "CDEF4567"
VAULT = "1111111111111111"


@pytest.fixture
def reading(tmp_path, monkeypatch):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\nsynthetic content\n")
    digest = "md5:" + hashlib.md5(pdf.read_bytes()).hexdigest()
    source = tmp_path / "source"
    source.mkdir()
    state = SimpleNamespace(pdf=pdf, source=source, revision="revision-a", calls=[],
                            local=True, available=True, reader_available=True,
                            reference_available=True, locator_hash=digest, library={"type": "user", "id": 123})
    state.resource = {"resource_id": f"paper:zotero:123:{PARENT}", "zotero": {"item_key": PARENT}}
    state.work = {"id": "work-a", "kind": "paper", "entity_ref": {
        "source_id": "source-a", "object_id": state.resource["resource_id"]}}
    state.asset = {"id": "asset-a", "kind": "zotero-pdf",
                   "uri": f"zotero://open-pdf/library/items/{PDF}?page=2"}
    state.items = {
        PARENT: {"key": PARENT, "library": state.library,
                 "data": {"itemType": "journalArticle"}},
        PDF: {"key": PDF, "library": state.library, "data": {
            "itemType": "attachment", "parentItem": PARENT, "contentType": "application/pdf"}},
        ANN: {"key": ANN, "library": state.library,
              "data": {"itemType": "annotation", "parentItem": PDF}},
    }

    class Registry:
        def __init__(self, path):
            state.calls.append("construct-registry")

        def revision(self):
            state.calls.append("registry-revision")
            return state.revision

        def resolve(self, source_id, *, capability):
            state.calls.append(("resolve", source_id, capability))
            assert source_id == "source-a" and capability == "read"
            return state.source

    class References:
        def current_unit(self, ref):
            state.calls.append(("unit", deepcopy(ref)))
            if not state.reference_available:
                raise RuntimeError("/private/sensitive/source")
            return {"source_id": "source-a", "resource_id": state.resource["resource_id"],
                    "ownership": {"status": "resolved"}, "catalog_resource": deepcopy(state.resource)}

    class Local:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get_item(self, key):
            state.calls.append(("get-item", key))
            if not state.available:
                raise ZoteroLocalUnavailable("/private/sensitive/storage")
            return deepcopy(state.items[key])

        def resolve_attachment_locator(self, key):
            state.calls.append(("locator", key))
            return ZoteroAttachmentLocator(key, str(state.library["id"]), state.locator_hash,
                                           state.pdf, state.pdf.name)

    class Reader:
        def __init__(self, root, **kwargs):
            state.calls.append(("reader", root))

        def probe_attachment(self, pdf_ref, *, verify_content=False):
            state.calls.append(("probe", pdf_ref.attachment_key, verify_content))
            return SimpleNamespace(available=state.local and state.reader_available,
                                   reason="/private/sensitive/reader")

    def obsidian_binding(root, *, config_path=None):
        state.calls.append(("vault", root))
        return SimpleNamespace(vault_root=root, vault_id=VAULT)

    monkeypatch.setattr(module, "KnowledgeSourceRegistry", Registry)
    monkeypatch.setattr(module, "resolve_obsidian_reader", obsidian_binding)
    state.gate = module.ExplorationReaderGate(tmp_path / "registry.json", reference_service=References(),
                                              adapter_factory=Local, reader_factory=Reader)
    state.zotflow = "obsidian://zotflow?" + (
        f"vault={VAULT}&type=open-attachment&libraryID=123&key={PDF}&page=2")
    return state


def test_constructor_and_unrelated_links_do_not_probe_any_source(reading):
    before = list(reading.calls)
    assert module.ExplorationReaderGate.handles("https://research.example/paper") is False
    assert reading.gate.availability(reading.work, {"id": "web", "uri": "https://research.example"}) == {
        "native_available": True}
    reading.gate.require_current(reading.work, {"id": "web", "uri": "https://research.example"})
    assert reading.calls == before


def test_pdf_opens_only_after_complete_availability_snapshot(reading):
    with pytest.raises(module.ReaderUnavailable) as error:
        reading.gate.require_current(reading.work, reading.asset)
    assert error.value.code == "refresh_required" and reading.calls == []
    assert reading.gate.availability(reading.work, reading.asset) == {"native_available": True}
    reading.gate.require_current(reading.work, reading.asset)
    assert ("locator", PDF) in reading.calls
    assert not any(call[0] == "reader" for call in reading.calls if isinstance(call, tuple))


@pytest.mark.parametrize("change", ["bytes", "uri", "reference", "revision", "locator", "parent", "library"])
def test_open_rechecks_snapshot_identity_and_real_pdf_bytes(reading, change):
    assert reading.gate.availability(reading.work, reading.asset)["native_available"]
    if change == "bytes":
        reading.pdf.write_bytes(b"%PDF-1.7\nreplacement bytes\n")
    elif change == "uri":
        reading.asset["uri"] = f"zotero://open-pdf/library/items/{PDF}?page=3"
    elif change == "reference":
        reading.work["entity_ref"]["source_id"] = "other"
    elif change == "revision":
        reading.revision = "revision-b"
    elif change == "locator":
        reading.locator_hash = "md5:" + "0" * 32
    elif change == "parent":
        reading.items[PDF]["data"]["parentItem"] = "DEFG5678"
    else:
        reading.items[PDF]["library"] = {"type": "group", "id": 999}
    with pytest.raises(module.ReaderUnavailable):
        reading.gate.require_current(reading.work, reading.asset)


@pytest.mark.parametrize("uri", [
    f"zotero://open-pdf/library/items/{PDF}?page=1&page=2",
    f"zotero://open-pdf/library/items/{PDF}?unknown=1",
    f"zotero://open-pdf/library/items/{PDF}?page=0",
    f"zotero://open-pdf/library/items/{PDF}?annotation=00000000",
    f"zotero://open-pdf/groups/999/items/{PDF}",
    f"zotero://user@open-pdf/library/items/{PDF}",
    f"zotero://open-pdf/library/items/{PDF}#fragment",
    f"obsidian://zotflow?vault={VAULT}&type=open-attachment&libraryID=123&key={PDF}&key={ANN}",
    f"obsidian://zotflow?vault={VAULT}&type=delete&libraryID=123&key={PDF}",
    f"obsidian://zotflow?vault={VAULT}&type=open-attachment&libraryID=123&key={PDF}&url=evil",
])
def test_invalid_reader_uris_are_diagnosed_without_success(reading, uri):
    reading.asset["uri"] = uri
    assert module.ExplorationReaderGate.handles(uri)
    result = reading.gate.availability(reading.work, reading.asset)
    assert result["native_available"] is False and result["native_reason_code"]


def test_zotero_annotation_requires_an_annotation_of_this_pdf(reading):
    reading.asset["uri"] += f"&annotation={ANN}"
    assert reading.gate.availability(reading.work, reading.asset)["native_available"]
    reading.items[ANN]["data"]["parentItem"] = "DEFG5678"
    with pytest.raises(module.ReaderUnavailable):
        reading.gate.require_current(reading.work, reading.asset)


@pytest.mark.parametrize("action", ["open-attachment", "open-annotation"])
def test_zotflow_requires_matching_vault_and_live_local_probe(reading, action):
    reading.asset["uri"] = reading.zotflow
    if action == "open-annotation":
        reading.asset["uri"] = reading.zotflow.replace("open-attachment", action).replace(f"key={PDF}", f"key={ANN}")
    reading.asset["kind"] = "other"
    assert reading.gate.availability(reading.work, reading.asset)["native_available"]
    assert ("probe", PDF, True) in reading.calls
    reading.local = False
    with pytest.raises(module.ReaderUnavailable) as error:
        reading.gate.require_current(reading.work, reading.asset)
    assert error.value.code == "zotflow_unavailable"


def test_zotflow_wrong_vault_is_not_a_launch_destination(reading):
    reading.asset["uri"] = reading.zotflow.replace(VAULT, "2222222222222222")
    result = reading.gate.availability(reading.work, reading.asset)
    assert result["native_available"] is False and result["native_reason_code"] == "identity_mismatch"
    assert not any(call[0] == "probe" for call in reading.calls if isinstance(call, tuple))


@pytest.mark.parametrize("failure", ["api", "unit", "file", "ownership"])
def test_failure_reasons_never_expose_paths_or_secrets(reading, failure):
    if failure == "api":
        reading.available = False
    elif failure == "unit":
        reading.reference_available = False
    elif failure == "file":
        reading.pdf.unlink()
    else:
        reading.resource["resource_id"] = f"paper:zotero:999:{PARENT}"
    result = reading.gate.availability(reading.work, reading.asset)
    assert result["native_available"] is False and result["native_reason_code"]
    assert "/private" not in result["native_reason"] and str(reading.source) not in str(result)


def test_group_pdf_requires_exact_observed_library(reading):
    reading.library.update(type="group", id=456)
    reading.resource["resource_id"] = f"paper:zotero:456:{PARENT}"
    reading.work["entity_ref"]["object_id"] = reading.resource["resource_id"]
    reading.asset["uri"] = f"zotero://open-pdf/groups/456/items/{PDF}"
    assert reading.gate.availability(reading.work, reading.asset)["native_available"]
    reading.gate.require_current(reading.work, reading.asset)


def test_failure_clears_previously_available_snapshot(reading):
    assert reading.gate.availability(reading.work, reading.asset)["native_available"]
    reading.available = False
    assert not reading.gate.availability(reading.work, reading.asset)["native_available"]
    reading.available = True
    with pytest.raises(module.ReaderUnavailable) as error:
        reading.gate.require_current(reading.work, reading.asset)
    assert error.value.code == "refresh_required"


def _analysis_zotflow_uri(page_index):
    from scholar_workflow.analysis.models import AnalysisReader, ZoteroPdfSpan
    from scholar_workflow.analysis.reference_rendering import reference_source_link

    span = ZoteroPdfSpan(library_type="personal", library_id="123", attachment_key=PDF,
                         content_hash="md5:" + "a" * 32, page_index=page_index)
    rendered = reference_source_link(span, "zh", reader=AnalysisReader(
        kind="zotflow_library", vault_id=VAULT,
    ))
    return rendered.split("](", 1)[1][:-1]


@pytest.mark.parametrize("page_index", [0, 3, 44])
def test_analysis_generated_zotflow_navigation_is_preserved_and_locally_checked(reading, page_index):
    uri = _analysis_zotflow_uri(page_index)
    reading.asset["uri"] = uri
    assert reading.gate.availability(reading.work, reading.asset) == {"native_available": True}
    parsed = module.parse_reading_uri(uri)
    assert parsed["uri"] == uri and parsed["navigation"] == {"pageIndex": page_index}
    assert parsed["page"] is None and parsed["key"] == PDF
    assert parsed["library"] == "123" and parsed["annotation"] is None
    assert ("probe", PDF, True) in reading.calls
    assert reading.gate._snapshots[reading.work["id"], reading.asset["id"]][0][2] == uri
    reading.gate.require_current(reading.work, reading.asset)
    reading.asset["uri"] = _analysis_zotflow_uri(page_index + 1)
    with pytest.raises(module.ReaderUnavailable) as conflict:
        reading.gate.require_current(reading.work, reading.asset)
    assert conflict.value.code == "refresh_required"


@pytest.mark.parametrize("navigation", [
    '{"pageIndex":0,"pageIndex":1}',
    '{"pageIndex":0,"\\u0070ageIndex":1}',
    '{"pageIndex":0,"zoom":1}',
    '{"pageIndex":{"pageIndex":0}}',
    '{"pageIndex":[0]}',
    '{"pageIndex":true}',
    '{"pageIndex":false}',
    '{"pageIndex":-1}',
    '{"pageIndex":0.0}',
    '{"pageIndex":"0"}',
    '{"pageIndex":null}',
    '{"pageIndex":NaN}',
    '{"pageIndex":Infinity}',
    '{}', '[]', 'null', '0', 'not-json', '{"pageIndex":0,}',
])
def test_navigation_json_is_strict_and_rejected_before_external_checks(reading, navigation):
    reading.asset["uri"] = reading.zotflow.removesuffix("&page=2") + "&navigation=" + quote(
        navigation, safe="",
    )
    result = reading.gate.availability(reading.work, reading.asset)
    assert result["native_available"] is False
    assert result["native_reason_code"] == "invalid_reader_uri"
    assert reading.calls == []


@pytest.mark.parametrize("query", [
    "&navigation=%7B%22pageIndex%22%3A0%7D&navigation=%7B%22pageIndex%22%3A1%7D",
    "&navigation=%7B%22pageIndex%22%3A0%7D&%6eavigation=%7B%22pageIndex%22%3A1%7D",
    "&navigation=%7B%22pageIndex%22%3A0%7D&page=1",
    "&page=1&navigation=%7B%22pageIndex%22%3A0%7D",
])
def test_navigation_duplicate_parameters_and_page_conflicts_are_rejected(reading, query):
    uri = reading.zotflow.removesuffix("&page=2") + query
    with pytest.raises(module.ReaderUnavailable) as error:
        module._parse(uri)
    assert error.value.code == "invalid_reader_uri" and reading.calls == []


def test_public_parser_keeps_existing_pages_and_real_annotation_identity(reading):
    uri = reading.asset["uri"] + f"&annotation={ANN}"
    parsed = module.parse_reading_uri(uri)
    assert parsed["uri"] == uri and parsed["page"] == 2 and parsed["navigation"] is None
    assert parsed["annotation"] == ANN and parsed["key"] == PDF
    assert module._parse(uri) == parsed
    reading.asset["uri"] = uri
    assert reading.gate.availability(reading.work, reading.asset)["native_available"]


def test_deep_nested_navigation_fails_closed(reading):
    navigation = '{"pageIndex":' + '[' * 1100 + '0' + ']' * 1100 + '}'
    uri = reading.zotflow.removesuffix("&page=2") + "&navigation=" + navigation
    with pytest.raises(module.ReaderUnavailable) as error:
        module._parse(uri)
    assert error.value.code == "invalid_reader_uri" and reading.calls == []
