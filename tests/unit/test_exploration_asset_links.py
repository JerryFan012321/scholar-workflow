"""Synthetic resource-link contracts; no files, servers or applications are opened."""

from copy import deepcopy

import pytest

from scholar_workflow.workflows.exploration_assets import resource_links

PARENT = "ABCD2345"
PDF = "BCDE3456"
NOTE = "CDEF4567"
OTHER = "DEFG5678"
WEB = "EFGH6789"


def resource(**identifiers):
    return {"resource_id": "paper:fixture", "identifiers": identifiers,
            "zotero": {"item_key": PARENT, "attachment_key": PDF}}


def parent(*, library_type="user", library_id=123):
    return {"key": PARENT, "library": {"type": library_type, "id": library_id},
            "data": {"key": PARENT, "itemType": "journalArticle", "title": "A paper"}}


def child(key, kind="attachment", **data):
    return {"key": key, "library": {"type": "user", "id": 123},
            "data": {"key": key, "parentItem": PARENT, "itemType": kind, **data}}


def uris(result):
    return [link["uri"] for link in result["links"]]


def test_source_identifiers_work_offline_and_no_zotero_identity_is_guessed():
    source = resource(url="https://research.example/paper", doi="10.1234/a.b", arxiv="2401.12345v2")
    original = deepcopy(source)
    result = resource_links(source)
    assert set(uris(result)) == {"https://research.example/paper", "https://doi.org/10.1234/a.b",
                                 "https://arxiv.org/abs/2401.12345v2"}
    assert any("Zotero" in note and "未读取" in note for note in result["notes"])
    assert source == original and not any(uri.startswith("zotero:") for uri in uris(result))
    assert all(set(link) == {"object_id", "title", "kind", "uri"} for link in result["links"])


@pytest.mark.parametrize("uri", [
    "http://research.example/paper", "javascript:alert(1)", "https://user:secret@research.example/",
    "https://localhost/paper", "https://sub.localhost/", "https://127.0.0.1/paper",
    "https://[::1]/", "https://[::ffff:127.0.0.1]/", "https://127.1/",
    "https://2130706433/", "https://research.example\\@127.0.0.1/",
    "https://research.example/\nsecret", "https://research.example:bad/", "https:///empty",
    "https://localhost。/", "https://127。0。0。1/", "https://localhost．/",
    "https://１２７。０。０。１/",
])
def test_unsafe_original_urls_are_reported_and_never_emitted(uri):
    result = resource_links(resource(url=uri))
    assert result["links"] == [] and any("网页" in note for note in result["notes"])


@pytest.mark.parametrize("identifiers", [
    {"doi": "not-a-doi"}, {"arxiv": "../../bad"}, {"arxiv": "2401.12345?download=1"},
    {"doi": "10.1234/space here"}, {"arxiv": []},
])
def test_malformed_identifiers_are_diagnosed_without_fabricated_links(identifiers):
    result = resource_links(resource(**identifiers))
    assert result["links"] == [] and len(result["notes"]) >= 2


def test_legacy_arxiv_and_doi_prefixes_are_normalized_without_dropping_versions():
    result = resource_links(resource(arxiv="arXiv:cs/9901001v3", doi="doi:10.1234/test (one)"))
    assert "https://arxiv.org/abs/cs/9901001v3" in uris(result)
    assert any("DOI" in note for note in result["notes"])


def test_user_library_links_use_confirmed_children_and_are_stable():
    children = [child(PDF, contentType="application/pdf", title="Main PDF"),
                child(NOTE, "note", note="<p>A note</p>"),
                child(OTHER, contentType="application/zip", title="Supplement"),
                child(WEB, linkMode="linked_url", url="https://code.example/repo", title="Code")]
    source, paper = resource(), parent()
    before = deepcopy((source, paper, children))
    result = resource_links(source, paper, children)
    assert set(uris(result)) == {
        f"zotero://select/library/items/{PARENT}", f"zotero://open-pdf/library/items/{PDF}",
        f"zotero://select/library/items/{NOTE}", f"zotero://select/library/items/{OTHER}",
        f"zotero://select/library/items/{WEB}", "https://code.example/repo",
    }
    assert result["notes"] == []
    assert len({link["object_id"] for link in result["links"]}) == len(result["links"])
    assert result == resource_links(source, paper, deepcopy(children))
    assert before == (source, paper, children)


def test_group_library_paths_use_the_observed_group_not_the_host_user():
    pdf = child(PDF, contentType="application/pdf")
    pdf["library"] = {"type": "group", "id": 456}
    result = resource_links(resource(), parent(library_type="group", library_id=456), [pdf])
    assert set(uris(result)) == {f"zotero://select/groups/456/items/{PARENT}",
                                f"zotero://open-pdf/groups/456/items/{PDF}"}


@pytest.mark.parametrize("resource_id", [
    f"paper:zotero:456:{PARENT}", f"document:zotero:456:{PARENT}",
    f"paper:zotero:123:{OTHER}", f"document:zotero:123:{OTHER}",
])
def test_formal_resource_library_and_item_identity_must_agree_with_parent(resource_id):
    source = resource(url="https://research.example/paper")
    source["resource_id"] = resource_id
    result = resource_links(source, parent(), [])
    assert uris(result) == ["https://research.example/paper"]
    assert any("资源身份" in note for note in result["notes"])


@pytest.mark.parametrize("kind", ["paper", "document"])
def test_matching_formal_resource_identity_remains_usable(kind):
    source = resource()
    source["resource_id"] = f"{kind}:zotero:123:{PARENT}"
    result = resource_links(source, parent(), [child(PDF, contentType="application/pdf")])
    assert result["notes"] == []
    assert f"zotero://open-pdf/library/items/{PDF}" in uris(result)


def test_confirmed_zotero_metadata_supplies_missing_original_links():
    source, paper = resource(), parent()
    source["resource_id"] = f"paper:zotero:123:{PARENT}"
    paper["data"].update(url="https://arxiv.org/abs/2603.14482", DOI="10.48550/arXiv.2603.14482")
    before = deepcopy((source, paper))
    result = resource_links(source, paper, [])
    assert "https://arxiv.org/abs/2603.14482" in uris(result)
    assert "https://doi.org/10.48550/arXiv.2603.14482" in uris(result)
    assert before == (source, paper)
    paper["key"] = OTHER
    assert not any(uri.startswith("https:") for uri in uris(resource_links(source, paper, [])))


@pytest.mark.parametrize("url", ["https://127.0.0.1/", "javascript:alert(1)", "https://user:secret@example.test/"])
def test_confirmed_parent_url_still_uses_public_url_safety_checks(url):
    paper = parent()
    paper["data"]["url"] = url
    assert not any(uri.startswith("https:") for uri in uris(resource_links(resource(), paper, [])))


def test_safe_international_domain_remains_a_public_web_entry():
    source_url = "https://例子.example/paper"
    result = resource_links(resource(url=source_url))
    assert uris(result) == [source_url]


@pytest.mark.parametrize("change", [
    lambda p: p.update(key=PDF), lambda p: p.update(deleted=True),
    lambda p: p["data"].update(deleted=True), lambda p: p["data"].update(itemType="note"),
    lambda p: p["data"].update(key=PDF), lambda p: p.update(library={"id": 123}),
    lambda p: p.update(library={"type": "unknown", "id": 123}),
    lambda p: p.update(library={"type": [], "id": 123}),
    lambda p: p.update(library={"type": "user", "id": True}),
    lambda p: p.update(library={"type": "user", "id": 0}),
])
def test_invalid_parent_identity_or_library_cannot_supply_native_links(change):
    paper = parent()
    change(paper)
    result = resource_links(resource(), paper, [child(PDF, contentType="application/pdf")])
    assert result["links"] == [] and result["notes"]


@pytest.mark.parametrize("change", [
    lambda c: c["data"].update(parentItem=OTHER),
    lambda c: c.update(library={"type": "user", "id": 999}),
    lambda c: c.update(library={"type": "group", "id": 123}),
    lambda c: c.update(key="00000000"), lambda c: c["data"].update(key=OTHER),
    lambda c: (c.update(key=PARENT), c["data"].update(key=PARENT)),
    lambda c: c["data"].update(deleted=True), lambda c: c.update(deleted=True),
    lambda c: c["data"].update(itemType="annotation"),
])
def test_unrelated_or_invalid_children_are_diagnosed_instead_of_misassociated(change):
    pdf = child(PDF, contentType="application/pdf")
    change(pdf)
    result = resource_links(resource(), parent(), [pdf])
    assert uris(result) == [f"zotero://select/library/items/{PARENT}"]
    assert result["notes"]


def test_duplicate_child_keys_are_explicit_and_not_repeated_as_assets():
    pdf = child(PDF, contentType="application/pdf")
    result = resource_links(resource(), parent(), [pdf, deepcopy(pdf)])
    assert any("重复" in note for note in result["notes"])
    assert uris(result).count(f"zotero://open-pdf/library/items/{PDF}") <= 1


def test_malformed_child_rows_and_missing_declared_attachment_remain_visible():
    result = resource_links(resource(), parent(), [None, {}, "bad"])
    assert len(result["notes"]) >= 4
    assert any("已登记" in note and "附件" in note for note in result["notes"])
    assert uris(result) == [f"zotero://select/library/items/{PARENT}"]


def test_unknown_child_inventory_is_distinct_from_an_empty_confirmed_list():
    result = resource_links(resource(), parent())
    assert uris(result) == [f"zotero://select/library/items/{PARENT}"]
    assert any("子条目" in note and "未读取" in note for note in result["notes"])
    assert any("附件" in note for note in resource_links(resource(), parent(), [])["notes"])


def test_equal_source_urls_are_deduplicated_and_no_code_or_model_url_is_invented():
    result = resource_links(resource(url="https://doi.org/10.1234/a", doi="10.1234/a"))
    assert uris(result) == ["https://doi.org/10.1234/a"]
    assert len({link["object_id"] for link in result["links"]}) == 1
    assert not any("github" in uri or "huggingface" in uri for uri in uris(result))


def test_invalid_linked_url_is_reported_but_its_valid_native_attachment_remains():
    linked = child(WEB, linkMode="linked_url", url="https://user:secret@code.example/repo")
    result = resource_links(resource(), parent(), [linked, child(PDF, contentType="application/pdf")])
    assert f"zotero://select/library/items/{WEB}" in uris(result)
    assert all("secret" not in uri for uri in uris(result))
    assert result["notes"]


def test_unstructured_inputs_return_diagnostics_instead_of_following_untrusted_data():
    for source in (None, [], {"identifiers": [], "zotero": "bad"}):
        result = resource_links(source)
        assert result["links"] == [] and result["notes"]
