from click.testing import CliRunner

from scholar_workflow.cli import main


def test_experiment_cli_exposes_only_record_management_primitives() -> None:
    result = CliRunner().invoke(main, ["experiment", "--help"])

    assert result.exit_code == 0, result.output
    for command in (
        "new-run",
        "target-add",
        "new-attempt",
        "start-attempt",
        "finalize-attempt",
        "validate",
        "promote",
        "record-remote",
        "index",
        "migrate-plan",
    ):
        assert command in result.output
    assert "execute" not in result.output
    assert "verify-backup" not in result.output


def test_experiment_cli_maps_contract_rejection_to_exit_2(tmp_path) -> None:
    result = CliRunner().invoke(
        main,
        ["experiment", "validate", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 2
    assert "project-layout.json is required" in result.output
