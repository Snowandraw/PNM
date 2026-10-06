from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from pnm.benchmarks.cpu import load_benchmark_settings, run_benchmark

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_cpu_benchmark_writes_reproducible_artifacts(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.toml"
    dataset_path.write_text(
        """
[dataset]
schema_version = 1
name = "test-suite"
seed = 7
dtype = "float32"
generator = "numpy.random.Generator(PCG64)"

[vector]
sizes = [16]

[matrix]
sizes = [4]

[records]
counts = [32]
histogram_bins = 16
filter_threshold = 0.0

[payload]
sizes = [64]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "results"
    config_path = tmp_path / "cpu.toml"
    config_path.write_text(
        f"""
[experiment]
name = "cpu-test"
seed = 7

[workload]
name = "cpu-operator-suite-v1"
batch_size = 1

[hardware]
memory_type = "test"
near_memory_enabled = false

[output]
directory = "{output_root.as_posix()}"

[cpu_benchmark]
dataset = "{dataset_path.as_posix()}"
warmup_iterations = 0
measured_iterations = 1
target_sample_ms = 1
operators = [
  "copy",
  "add",
  "multiply",
  "relu",
  "sum",
  "gather",
  "transpose_copy",
  "threshold_count",
  "filter_compact",
  "histogram",
  "crc32",
  "matmul",
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result_directory = run_benchmark(config_path)

    metrics = json.loads((result_directory / "metrics.json").read_text(encoding="utf-8"))
    manifest = json.loads((result_directory / "manifest.json").read_text(encoding="utf-8"))
    assert len(metrics["metrics"]) == 12
    assert {row["correctness_status"] for row in metrics["metrics"]} == {"passed"}
    assert manifest["experiment"]["near_memory_enabled"] is False
    assert manifest["execution"]["requested_cpu_affinity"] is None
    assert manifest["runtime"]["cpu_model"]
    assert (result_directory / "summary.csv").is_file()
    assert (result_directory / "config.toml").is_file()
    assert (result_directory / "dataset.toml").is_file()


def test_cpu_benchmark_rejects_unknown_operator(tmp_path: Path) -> None:
    config_path = tmp_path / "invalid.toml"
    config_path.write_text(
        """
[experiment]
name = "cpu-test"
seed = 7

[workload]
name = "cpu-operator-suite-v1"
batch_size = 1

[hardware]
memory_type = "test"
near_memory_enabled = false

[output]
directory = "outputs"

[cpu_benchmark]
dataset = "data/sample/cpu_operator_suite.toml"
warmup_iterations = 0
measured_iterations = 1
target_sample_ms = 1
operators = ["not-an-operator"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported CPU operators"):
        load_benchmark_settings(config_path)


def test_server_pcore_configuration_loads_execution_controls() -> None:
    settings = load_benchmark_settings(REPOSITORY_ROOT / "configs/cpu_server_285k_pcore.toml")

    assert settings.experiment.name == "cpu-baseline-core-ultra-9-285k-pcore-single"
    assert settings.execution_profile == "pcore-single-cpu2"
    assert settings.cpu_affinity == (2,)
    assert settings.thread_count == 1
    assert len(settings.operators) == 12
