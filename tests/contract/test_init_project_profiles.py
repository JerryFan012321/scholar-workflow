import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "init-project" / "scripts" / "init_project.py"
CATALOG = ROOT / "skills" / "init-project" / "references" / "source-profiles.json"


def run_init(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_profile_catalog_has_six_profiles_and_cannot_claim_outer_state() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    catalog_schema = json.loads(
        (ROOT / "contracts" / "source-profiles.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(catalog, catalog_schema)
    assert set(catalog["profiles"]) == {
        "paper-method",
        "multi-stage-3d",
        "research-framework",
        "foundation-model",
        "world-model",
        "training-platform",
    }
    for group in (catalog["profiles"], catalog["addons"]):
        for entry in group.values():
            assert not {
                path.split("/", 1)[0] for path in entry["paths"]
            }.intersection({"dataset", "docs", "env", "experiments"})


def test_profile_plan_is_read_only_and_apply_is_stable(tmp_path: Path) -> None:
    target = tmp_path / "profile-project"
    args = (
        str(target),
        "--source-profile",
        "multi-stage-3d",
        "--package",
        "demo_3d",
        "--addon",
        "native-kernels",
    )
    planned = run_init("plan", *args)
    assert planned.returncode == 0, planned.stderr
    assert not target.exists()

    first = run_init("apply", *args)
    assert first.returncode == 0, first.stderr
    manifest_bytes = (target / "project-layout.json").read_bytes()
    assert (target / "src/demo_3d/renderers").is_dir()
    assert (target / "src/demo_3d/csrc").is_dir()

    second = run_init("apply", *args)
    assert second.returncode == 0, second.stderr
    assert (target / "project-layout.json").read_bytes() == manifest_bytes


def test_apply_rejects_profile_drift_before_writing(tmp_path: Path) -> None:
    target = tmp_path / "profile-project"
    initial = run_init(
        "apply", str(target), "--source-profile", "paper-method", "--package", "demo"
    )
    assert initial.returncode == 0, initial.stderr

    before = {
        path.relative_to(target): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    changed = run_init(
        "apply", str(target), "--source-profile", "world-model", "--package", "demo"
    )
    after = {
        path.relative_to(target): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    assert changed.returncode == 2
    assert "use migrate-plan" in changed.stdout
    assert before == after
    assert not (target / "src/demo/runtime/replay").exists()


def test_migrate_plan_reports_legacy_paths_without_changes(tmp_path: Path) -> None:
    target = tmp_path / "legacy"
    (target / "dataset_toolkits").mkdir(parents=True)
    marker = target / "dataset_toolkits" / "keep.py"
    marker.write_text("# keep\n", encoding="utf-8")

    result = run_init("migrate-plan", str(target))

    assert result.returncode == 0
    assert "[diagnostic] dataset_toolkits" in result.stdout
    assert "no paths were moved, removed, untracked, or written" in result.stdout
    assert marker.read_text(encoding="utf-8") == "# keep\n"
    assert not (target / "project-layout.json").exists()
