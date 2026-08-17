from pathlib import Path

import pytest

from pnm.config import load_experiment_config

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_baseline_config_loads() -> None:
    config = load_experiment_config(REPOSITORY_ROOT / "configs" / "baseline.toml")

    assert config.name == "baseline"
    assert config.seed == 42
    assert config.batch_size == 1
    assert config.near_memory_enabled is True


def test_missing_required_section_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid.toml"
    config_path.write_text("[experiment]\nname = 'bad'\nseed = 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="workload"):
        load_experiment_config(config_path)
