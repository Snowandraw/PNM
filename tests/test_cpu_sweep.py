from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from pnm.benchmarks.cpu import load_benchmark_settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cpu_sweep", REPOSITORY_ROOT / "scripts/run_cpu_sweep.py"
)
assert SPEC is not None and SPEC.loader is not None
SWEEP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SWEEP)


@pytest.mark.parametrize(
    ("threads", "cpus"),
    [(2, (2, 5)), (4, (0, 1, 2, 5)), (8, tuple(range(8)))],
)
def test_pcore_multithread_configurations(threads: int, cpus: tuple[int, ...]) -> None:
    settings = load_benchmark_settings(
        REPOSITORY_ROOT / f"configs/cpu_server_285k_pcore_{threads}t.toml"
    )
    assert settings.cpu_affinity == cpus
    assert settings.thread_count == threads
    assert settings.warmup_iterations == 5
    assert settings.measured_iterations == 15
    assert settings.target_sample_ms == 50
    assert len(settings.operators) == 12


def test_sweep_rotates_profiles_without_changing_membership() -> None:
    configs = [Path("p1"), Path("e1"), Path("p2")]
    assert SWEEP.configuration_order(configs, 0) == configs
    assert SWEEP.configuration_order(configs, 1) == [configs[1], configs[2], configs[0]]
    assert SWEEP.configuration_order(configs, 3) == configs


def test_sweep_aggregates_independent_medians_and_rejects_failures(tmp_path: Path) -> None:
    runs = []
    for index, value in enumerate([1.0, 2.0, 6.0]):
        directory = tmp_path / str(index)
        directory.mkdir()
        row = {
            "operator": "copy",
            "variant": "contiguous-f32",
            "dtype": "float32",
            "shape": "16",
            "median_ms": value,
            "coefficient_of_variation": 0.01,
            "correctness_status": "passed",
        }
        (directory / "metrics.json").write_text(json.dumps({"metrics": [row]}), encoding="utf-8")
        runs.append({"profile": "p1", "result_directory": str(directory)})
    summary = SWEEP.summarize_runs(runs)
    assert len(summary) == 1
    assert summary[0]["run_count"] == 3
    assert summary[0]["median_of_run_medians_ms"] == 2.0
    assert summary[0]["min_run_median_ms"] == 1.0
    assert summary[0]["max_run_median_ms"] == 6.0
    assert summary[0]["between_run_cv"] == pytest.approx(0.7200822998)
    failed_path = tmp_path / "2" / "metrics.json"
    failed_metrics = json.loads(failed_path.read_text(encoding="utf-8"))
    failed_metrics["metrics"][0]["correctness_status"] = "failed"
    failed_path.write_text(json.dumps(failed_metrics), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Failed correctness"):
        SWEEP.summarize_runs(runs)


def test_sweep_rejects_invalid_rounds_before_writing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rounds must be positive"):
        SWEEP.run_sweep([], 0, tmp_path / "unused")
    assert not (tmp_path / "unused").exists()
