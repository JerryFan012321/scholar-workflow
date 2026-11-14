"""Independent file-operation preview contracts; no business files or transports."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "experiment_materials",
    Path(__file__).resolve().parents[2] / "skills/manage-experiments/scripts/materials.py",
)
materials = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(materials)


def selected(path="result.csv", kind="result", keep="retain", send=True):
    return {"path": path, "kind": kind, "use": "Compare the selected conditions",
            "keep": keep, "return": send}


def selection(*items):
    return {"schema_version": 1, "files": list(items)}


def test_preview_accounts_bytes_without_reading_retained_model(tmp_path, monkeypatch):
    (tmp_path / "result.csv").write_bytes(b"value\n5\n")
    (tmp_path / "model.bin").write_bytes(b"opaque-model")
    (tmp_path / "cache.tmp").write_bytes(b"rebuild")
    (tmp_path / "unlisted.dat").write_bytes(b"not-inspected")
    original = materials.os.open

    def guarded(path, *args, **kwargs):
        assert str(path) != "model.bin", "Retained model payload must not be opened"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(materials.os, "open", guarded)
    plan = materials.make_plan(tmp_path, selection(
        selected(), selected("model.bin", "model", send=False),
        selected("cache.tmp", "temporary", "cleanup", False)))
    assert [o["size"] for o in plan["observed"]] == [8, 12, 7]
    assert "sha256" not in plan["observed"][1]
    assert len(plan["observed"][0]["sha256"]) == 64
    assert "Return: 8 bytes" in materials.markdown(plan)
    assert "Cleanup: 7 bytes" in materials.markdown(plan)
    assert "Unlisted files" in materials.markdown(plan)
    assert (tmp_path / "cache.tmp").read_bytes() == b"rebuild"
    materials.verify(tmp_path, plan)


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside", "x/../../outside", "./x",
                                 "x//y", "x/", ".", ".git/config", "x\ny", "a\\b"])
def test_unsafe_and_ambiguous_paths_refuse(path):
    with pytest.raises(ValueError):
        materials.validate_selection(selection(selected(path)))


@pytest.mark.parametrize("kind", ["model", "raw", "temporary", "input"])
def test_non_result_payload_cannot_return_even_when_small(tmp_path, kind):
    (tmp_path / "result.csv").write_text("1")
    with pytest.raises(ValueError, match="analytical"):
        materials.make_plan(tmp_path, selection(selected(kind=kind)))


@pytest.mark.parametrize("keep", ["cleanup", "undecided"])
def test_conflicting_return_and_keep_refuse(keep):
    with pytest.raises(ValueError):
        materials.validate_selection(selection(selected(keep=keep)))


def test_undecided_material_remains_visible(tmp_path):
    (tmp_path / "result.csv").write_text("unknown")
    plan = materials.make_plan(tmp_path, selection(selected(keep="undecided", send=False)))
    assert "undecided" in materials.markdown(plan)
    assert "sha256" not in plan["observed"][0]


def test_duplicate_or_missing_purpose_refuse():
    with pytest.raises(ValueError, match="Duplicate"):
        materials.validate_selection(selection(selected(), selected()))
    item = selected()
    item["use"] = " "
    with pytest.raises(ValueError, match="use"):
        materials.validate_selection(selection(item))


def test_symlink_file_directory_and_root_refuse(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "value").write_text("original")
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    (tmp_path / "file-link").symlink_to(real / "value")
    for root, path in [(tmp_path, "link/value"), (tmp_path, "file-link"), (tmp_path / "link", "value")]:
        with pytest.raises((ValueError, OSError)):
            materials.make_plan(root, selection(selected(path)))


def test_directory_and_missing_file_refuse(tmp_path):
    (tmp_path / "folder").mkdir()
    for path in ["folder", "absent.csv"]:
        with pytest.raises((ValueError, OSError)):
            materials.make_plan(tmp_path, selection(selected(path)))


def test_changed_same_length_file_invalidates_preview(tmp_path):
    p = tmp_path / "result.csv"
    p.write_text("before")
    plan = materials.make_plan(tmp_path, selection(selected()))
    p.write_text("after!")
    with pytest.raises(ValueError, match="changed"):
        materials.verify(tmp_path, plan)
    assert p.read_text() == "after!"


def test_recreated_same_byte_file_and_different_root_refuse(tmp_path):
    p = tmp_path / "result.csv"
    p.write_text("stable")
    plan = materials.make_plan(tmp_path, selection(selected()))
    replacement = tmp_path / "replacement"
    replacement.write_text("stable")
    replacement.replace(p)
    with pytest.raises(ValueError, match="changed"):
        materials.verify(tmp_path, plan)
    other = tmp_path / "other"
    other.mkdir()
    (other / "result.csv").write_text("stable")
    with pytest.raises(ValueError, match="changed"):
        materials.verify(other, plan)


def test_tampered_plan_refuses_and_cli_is_read_only(tmp_path, capsys):
    (tmp_path / "result.csv").write_text("12")
    policy = tmp_path / "selection.json"
    policy.write_text(json.dumps(selection(selected())))
    assert materials.main(["plan", str(tmp_path), str(policy), "--json"]) == 0
    saved = json.loads(capsys.readouterr().out)
    tampered = copy.deepcopy(saved)
    tampered["selection"]["files"][0]["keep"] = "cleanup"
    with pytest.raises(ValueError, match="changed"):
        materials.verify(tmp_path, tampered)
    snapshot = tmp_path / "plan.json"
    snapshot.write_text(json.dumps(saved))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert materials.main(["verify", str(tmp_path), str(snapshot)]) == 0
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
