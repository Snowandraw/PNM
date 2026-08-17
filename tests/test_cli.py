from pathlib import Path

from pytest import CaptureFixture

from pnm.cli import main

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_cli_reports_selected_configuration(capsys: CaptureFixture[str]) -> None:
    exit_code = main(["--config", str(REPOSITORY_ROOT / "configs" / "baseline.toml")])

    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Experiment: baseline" in output
    assert "Near-memory enabled: True" in output
