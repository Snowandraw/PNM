"""Reproducible NumPy CPU operator benchmark.

The suite intentionally keeps input generation and correctness validation outside
the timed region. Its JSON output is a CPU baseline that future DPU/NPU backends
can reuse; it is not a claim about physical DDR bandwidth or hardware counters.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
import tomllib
import warnings
import zlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pnm.config import ExperimentConfig, load_experiment_config

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SUPPORTED_OPERATORS = frozenset(
    {
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
    }
)
THREAD_ENVIRONMENT_VARIABLES = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


@dataclass(frozen=True)
class DatasetSpec:
    """Description of deterministic inputs generated at runtime."""

    schema_version: int
    name: str
    seed: int
    dtype: str
    generator: str
    vector_sizes: tuple[int, ...]
    matrix_sizes: tuple[int, ...]
    record_counts: tuple[int, ...]
    histogram_bins: int
    filter_threshold: float
    payload_sizes: tuple[int, ...]


@dataclass(frozen=True)
class BenchmarkSettings:
    """CPU benchmark options loaded from an experiment configuration."""

    experiment: ExperimentConfig
    config_path: Path
    dataset_path: Path
    warmup_iterations: int
    measured_iterations: int
    target_sample_ms: float
    operators: tuple[str, ...]


@dataclass
class BenchmarkCase:
    """One allocated data shape and one timed operator."""

    operator: str
    variant: str
    shape: str
    dtype: str
    elements: int
    input_bytes: int
    output_bytes: int
    logical_bytes: int
    floating_point_operations: int
    invoke: Callable[[], None]
    validate: Callable[[], tuple[bool, str | None]]


def build_parser() -> argparse.ArgumentParser:
    """Create the dedicated CPU benchmark CLI parser."""
    parser = argparse.ArgumentParser(
        description="Run the reproducible NumPy CPU operator baseline."
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to a TOML experiment configuration with a [cpu_benchmark] section.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional output root. Defaults to [output].directory in the configuration.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run a CPU benchmark and print its artifact directory."""
    args = build_parser().parse_args(argv)
    output_path = run_benchmark(args.config, output_root=args.output_dir)
    print(f"CPU benchmark completed: {output_path}")
    return 0


def run_benchmark(config_path: Path, output_root: Path | None = None) -> Path:
    """Run all selected CPU cases and persist a self-describing result bundle."""
    numpy = _load_numpy()
    settings = load_benchmark_settings(config_path)
    dataset = load_dataset_spec(settings.dataset_path)
    selected_operators = frozenset(settings.operators)
    started_at = datetime.now(UTC)

    rows: list[dict[str, object]] = []
    for vector_size in dataset.vector_sizes:
        rows.extend(
            _run_cases(
                _vector_cases(numpy, dataset, selected_operators, vector_size),
                settings,
                dataset,
            )
        )
    for matrix_size in dataset.matrix_sizes:
        rows.extend(
            _run_cases(
                _matrix_cases(numpy, dataset, selected_operators, matrix_size),
                settings,
                dataset,
            )
        )
    for record_count in dataset.record_counts:
        rows.extend(
            _run_cases(
                _record_cases(numpy, dataset, selected_operators, record_count),
                settings,
                dataset,
            )
        )
    for payload_size in dataset.payload_sizes:
        rows.extend(
            _run_cases(
                _payload_cases(numpy, dataset, selected_operators, payload_size),
                settings,
                dataset,
            )
        )

    finished_at = datetime.now(UTC)
    result_directory = _create_result_directory(
        output_root or _resolve_output_root(settings.experiment),
        settings.experiment.name,
        settings.config_path,
    )
    manifest = _build_manifest(
        numpy=numpy,
        settings=settings,
        dataset=dataset,
        result_directory=result_directory,
        started_at=started_at,
        finished_at=finished_at,
    )
    _write_artifacts(result_directory, rows, manifest, settings)
    return result_directory


def load_benchmark_settings(config_path: Path) -> BenchmarkSettings:
    """Load the base experiment config plus the CPU-specific section."""
    resolved_config_path = config_path.resolve()
    experiment = load_experiment_config(resolved_config_path)
    raw = _load_toml(resolved_config_path)
    section = _mapping(raw, "cpu_benchmark", resolved_config_path)
    dataset_value = _required_string(section, "dataset", "cpu_benchmark")
    dataset_path = Path(dataset_value)
    if not dataset_path.is_absolute():
        dataset_path = REPOSITORY_ROOT / dataset_path

    operators_value = section.get("operators")
    if not isinstance(operators_value, list) or not operators_value:
        raise ValueError("cpu_benchmark.operators must be a non-empty TOML array")
    operators = tuple(operators_value)
    if any(not isinstance(operator, str) for operator in operators):
        raise ValueError("cpu_benchmark.operators must contain only strings")
    unknown_operators = sorted(set(operators) - SUPPORTED_OPERATORS)
    if unknown_operators:
        raise ValueError(f"Unsupported CPU operators: {', '.join(unknown_operators)}")
    if len(set(operators)) != len(operators):
        raise ValueError("cpu_benchmark.operators must not contain duplicates")

    return BenchmarkSettings(
        experiment=experiment,
        config_path=resolved_config_path,
        dataset_path=dataset_path.resolve(),
        warmup_iterations=_non_negative_int(section, "warmup_iterations", "cpu_benchmark"),
        measured_iterations=_positive_int(section, "measured_iterations", "cpu_benchmark"),
        target_sample_ms=_positive_number(section, "target_sample_ms", "cpu_benchmark"),
        operators=operators,
    )


def load_dataset_spec(path: Path) -> DatasetSpec:
    """Load and validate the data shapes used by the synthetic input generator."""
    resolved_path = path.resolve()
    raw = _load_toml(resolved_path)
    dataset = _mapping(raw, "dataset", resolved_path)
    vector = _mapping(raw, "vector", resolved_path)
    matrix = _mapping(raw, "matrix", resolved_path)
    records = _mapping(raw, "records", resolved_path)
    payload = _mapping(raw, "payload", resolved_path)

    dtype = _required_string(dataset, "dtype", "dataset")
    if dtype != "float32":
        raise ValueError("dataset.dtype must currently be 'float32'")

    return DatasetSpec(
        schema_version=_positive_int(dataset, "schema_version", "dataset"),
        name=_required_string(dataset, "name", "dataset"),
        seed=_non_negative_int(dataset, "seed", "dataset"),
        dtype=dtype,
        generator=_required_string(dataset, "generator", "dataset"),
        vector_sizes=_positive_int_tuple(vector, "sizes", "vector"),
        matrix_sizes=_positive_int_tuple(matrix, "sizes", "matrix"),
        record_counts=_positive_int_tuple(records, "counts", "records"),
        histogram_bins=_positive_int(records, "histogram_bins", "records"),
        filter_threshold=_number(records, "filter_threshold", "records"),
        payload_sizes=_positive_int_tuple(payload, "sizes", "payload"),
    )


def _vector_cases(
    numpy: Any,
    dataset: DatasetSpec,
    selected: frozenset[str],
    elements: int,
) -> list[BenchmarkCase]:
    """Build vector cases while keeping one working set alive at a time."""
    active = selected & {"copy", "add", "multiply", "relu", "sum", "gather"}
    if not active:
        return []

    generator = _rng(numpy, dataset.seed + elements)
    left = generator.standard_normal(elements, dtype=numpy.float32)
    right = generator.standard_normal(elements, dtype=numpy.float32)
    output = numpy.empty_like(left)
    itemsize = left.itemsize
    cases: list[BenchmarkCase] = []

    if "copy" in active:

        def invoke_copy() -> None:
            numpy.copyto(output, left)

        def validate_copy() -> tuple[bool, str | None]:
            return bool(numpy.array_equal(output, left)), "copy output differs from input"

        cases.append(
            BenchmarkCase(
                operator="copy",
                variant="contiguous-f32",
                shape=str(elements),
                dtype=dataset.dtype,
                elements=elements,
                input_bytes=left.nbytes,
                output_bytes=output.nbytes,
                logical_bytes=2 * elements * itemsize,
                floating_point_operations=0,
                invoke=invoke_copy,
                validate=validate_copy,
            )
        )

    if "add" in active:

        def invoke_add() -> None:
            numpy.add(left, right, out=output)

        def validate_add() -> tuple[bool, str | None]:
            valid = numpy.allclose(output, left + right, rtol=1e-6, atol=1e-6)
            return bool(valid), "add output failed validation"

        cases.append(
            BenchmarkCase(
                operator="add",
                variant="contiguous-f32",
                shape=str(elements),
                dtype=dataset.dtype,
                elements=elements,
                input_bytes=left.nbytes + right.nbytes,
                output_bytes=output.nbytes,
                logical_bytes=3 * elements * itemsize,
                floating_point_operations=elements,
                invoke=invoke_add,
                validate=validate_add,
            )
        )

    if "multiply" in active:

        def invoke_multiply() -> None:
            numpy.multiply(left, right, out=output)

        def validate_multiply() -> tuple[bool, str | None]:
            valid = numpy.allclose(output, left * right, rtol=1e-6, atol=1e-6)
            return bool(valid), "multiply output failed validation"

        cases.append(
            BenchmarkCase(
                operator="multiply",
                variant="contiguous-f32",
                shape=str(elements),
                dtype=dataset.dtype,
                elements=elements,
                input_bytes=left.nbytes + right.nbytes,
                output_bytes=output.nbytes,
                logical_bytes=3 * elements * itemsize,
                floating_point_operations=elements,
                invoke=invoke_multiply,
                validate=validate_multiply,
            )
        )

    if "relu" in active:

        def invoke_relu() -> None:
            numpy.maximum(left, 0.0, out=output)

        def validate_relu() -> tuple[bool, str | None]:
            valid = numpy.allclose(output, numpy.maximum(left, 0.0), rtol=0.0, atol=0.0)
            return bool(valid), "relu output failed validation"

        cases.append(
            BenchmarkCase(
                operator="relu",
                variant="contiguous-f32",
                shape=str(elements),
                dtype=dataset.dtype,
                elements=elements,
                input_bytes=left.nbytes,
                output_bytes=output.nbytes,
                logical_bytes=2 * elements * itemsize,
                floating_point_operations=elements,
                invoke=invoke_relu,
                validate=validate_relu,
            )
        )

    if "sum" in active:
        expected_sum = float(numpy.sum(left, dtype=numpy.float32))
        sum_result = [0.0]

        def invoke_sum() -> None:
            sum_result[0] = float(numpy.sum(left, dtype=numpy.float32))

        def validate_sum() -> tuple[bool, str | None]:
            valid = math.isclose(sum_result[0], expected_sum, rel_tol=1e-6, abs_tol=1e-6)
            return valid, "sum output failed validation"

        cases.append(
            BenchmarkCase(
                operator="sum",
                variant="contiguous-f32",
                shape=str(elements),
                dtype=dataset.dtype,
                elements=elements,
                input_bytes=left.nbytes,
                output_bytes=itemsize,
                logical_bytes=left.nbytes + itemsize,
                floating_point_operations=max(elements - 1, 0),
                invoke=invoke_sum,
                validate=validate_sum,
            )
        )

    if "gather" in active:
        indices = generator.integers(0, elements, size=elements, dtype=numpy.intp)

        def invoke_gather() -> None:
            numpy.take(left, indices, out=output)

        def validate_gather() -> tuple[bool, str | None]:
            return bool(numpy.array_equal(output, left[indices])), "gather output failed validation"

        cases.append(
            BenchmarkCase(
                operator="gather",
                variant="random-index-f32",
                shape=str(elements),
                dtype=dataset.dtype,
                elements=elements,
                input_bytes=left.nbytes + indices.nbytes,
                output_bytes=output.nbytes,
                logical_bytes=left.nbytes + indices.nbytes + output.nbytes,
                floating_point_operations=0,
                invoke=invoke_gather,
                validate=validate_gather,
            )
        )

    return cases


def _matrix_cases(
    numpy: Any,
    dataset: DatasetSpec,
    selected: frozenset[str],
    side: int,
) -> list[BenchmarkCase]:
    """Build layout-conversion and dense-linear-algebra cases."""
    active = selected & {"transpose_copy", "matmul"}
    if not active:
        return []

    generator = _rng(numpy, dataset.seed + (side << 8))
    source = generator.standard_normal((side, side), dtype=numpy.float32)
    output = numpy.empty_like(source)
    cases: list[BenchmarkCase] = []
    shape = f"({side}, {side})"

    if "transpose_copy" in active:

        def invoke_transpose() -> None:
            numpy.copyto(output, source.T)

        def validate_transpose() -> tuple[bool, str | None]:
            return bool(numpy.array_equal(output, source.T)), "transpose output failed validation"

        cases.append(
            BenchmarkCase(
                operator="transpose_copy",
                variant="materialized-f32",
                shape=shape,
                dtype=dataset.dtype,
                elements=source.size,
                input_bytes=source.nbytes,
                output_bytes=output.nbytes,
                logical_bytes=source.nbytes + output.nbytes,
                floating_point_operations=0,
                invoke=invoke_transpose,
                validate=validate_transpose,
            )
        )

    if "matmul" in active:
        right = generator.standard_normal((side, side), dtype=numpy.float32)
        product = numpy.empty_like(source)

        def invoke_matmul() -> None:
            numpy.matmul(source, right, out=product)

        def validate_matmul() -> tuple[bool, str | None]:
            return bool(numpy.isfinite(product).all()), "matmul produced a non-finite result"

        cases.append(
            BenchmarkCase(
                operator="matmul",
                variant="square-f32",
                shape=shape,
                dtype=dataset.dtype,
                elements=source.size,
                input_bytes=source.nbytes + right.nbytes,
                output_bytes=product.nbytes,
                logical_bytes=source.nbytes + right.nbytes + product.nbytes,
                floating_point_operations=2 * side * side * side,
                invoke=invoke_matmul,
                validate=validate_matmul,
            )
        )

    return cases


def _record_cases(
    numpy: Any,
    dataset: DatasetSpec,
    selected: frozenset[str],
    count: int,
) -> list[BenchmarkCase]:
    """Build 16-byte-record filtering and aggregation cases."""
    active = selected & {"threshold_count", "filter_compact", "histogram"}
    if not active:
        return []

    record_dtype = numpy.dtype(
        [
            ("flow_id", "<u4"),
            ("timestamp", "<u4"),
            ("length", "<u2"),
            ("flags", "<u2"),
            ("value", "<f4"),
        ]
    )
    generator = _rng(numpy, dataset.seed + (count << 2))
    records = numpy.empty(count, dtype=record_dtype)
    records["flow_id"] = generator.integers(
        0, dataset.histogram_bins, size=count, dtype=numpy.uint32
    )
    records["timestamp"] = numpy.arange(count, dtype=numpy.uint32)
    records["length"] = generator.integers(64, 1501, size=count, dtype=numpy.uint16)
    records["flags"] = generator.integers(0, 256, size=count, dtype=numpy.uint16)
    records["value"] = generator.standard_normal(count, dtype=numpy.float32)

    flow_ids = records["flow_id"]
    values = records["value"]
    mask = numpy.empty(count, dtype=numpy.bool_)
    expected_selected = int(numpy.count_nonzero(values > dataset.filter_threshold))
    cases: list[BenchmarkCase] = []

    if "threshold_count" in active:
        selected_count = [0]

        def invoke_threshold_count() -> None:
            numpy.greater(values, dataset.filter_threshold, out=mask)
            selected_count[0] = int(numpy.count_nonzero(mask))

        def validate_threshold_count() -> tuple[bool, str | None]:
            valid = selected_count[0] == expected_selected
            return valid, "threshold_count result failed validation"

        cases.append(
            BenchmarkCase(
                operator="threshold_count",
                variant="records-v1",
                shape=str(count),
                dtype="records-v1",
                elements=count,
                input_bytes=values.nbytes,
                output_bytes=mask.nbytes + 8,
                logical_bytes=values.nbytes + 2 * mask.nbytes + 8,
                floating_point_operations=count,
                invoke=invoke_threshold_count,
                validate=validate_threshold_count,
            )
        )

    if "filter_compact" in active:
        compacted = [numpy.empty(0, dtype=record_dtype)]

        def invoke_filter_compact() -> None:
            numpy.greater(values, dataset.filter_threshold, out=mask)
            compacted[0] = records[mask]

        def validate_filter_compact() -> tuple[bool, str | None]:
            valid = compacted[0].size == expected_selected
            if valid and compacted[0].size:
                valid = bool(numpy.all(compacted[0]["value"] > dataset.filter_threshold))
            return valid, "filter_compact result failed validation"

        cases.append(
            BenchmarkCase(
                operator="filter_compact",
                variant="records-v1",
                shape=str(count),
                dtype="records-v1",
                elements=count,
                input_bytes=records.nbytes,
                output_bytes=expected_selected * record_dtype.itemsize,
                logical_bytes=records.nbytes
                + mask.nbytes
                + expected_selected * record_dtype.itemsize,
                floating_point_operations=count,
                invoke=invoke_filter_compact,
                validate=validate_filter_compact,
            )
        )

    if "histogram" in active:
        histogram = [numpy.empty(0, dtype=numpy.int64)]

        def invoke_histogram() -> None:
            histogram[0] = numpy.bincount(flow_ids, minlength=dataset.histogram_bins)

        def validate_histogram() -> tuple[bool, str | None]:
            valid = histogram[0].size == dataset.histogram_bins
            if valid:
                valid = int(numpy.sum(histogram[0])) == count
            return valid, "histogram result failed validation"

        cases.append(
            BenchmarkCase(
                operator="histogram",
                variant=f"records-v1-{dataset.histogram_bins}-bins",
                shape=str(count),
                dtype="records-v1",
                elements=count,
                input_bytes=flow_ids.nbytes,
                output_bytes=dataset.histogram_bins * numpy.dtype(numpy.int64).itemsize,
                logical_bytes=flow_ids.nbytes
                + dataset.histogram_bins * numpy.dtype(numpy.int64).itemsize,
                floating_point_operations=0,
                invoke=invoke_histogram,
                validate=validate_histogram,
            )
        )

    return cases


def _payload_cases(
    numpy: Any,
    dataset: DatasetSpec,
    selected: frozenset[str],
    size: int,
) -> list[BenchmarkCase]:
    """Build checksum cases over deterministic high-entropy byte buffers."""
    if "crc32" not in selected:
        return []

    generator = _rng(numpy, dataset.seed + (size << 1))
    payload = generator.integers(0, 256, size=size, dtype=numpy.uint8)
    payload_view = memoryview(payload)
    expected_crc = zlib.crc32(payload_view)
    crc_result = [0]

    def invoke_crc32() -> None:
        crc_result[0] = zlib.crc32(payload_view)

    def validate_crc32() -> tuple[bool, str | None]:
        return crc_result[0] == expected_crc, "crc32 result failed validation"

    return [
        BenchmarkCase(
            operator="crc32",
            variant="high-entropy-u8",
            shape=str(size),
            dtype="uint8",
            elements=size,
            input_bytes=payload.nbytes,
            output_bytes=4,
            logical_bytes=payload.nbytes + 4,
            floating_point_operations=0,
            invoke=invoke_crc32,
            validate=validate_crc32,
        )
    ]


def _run_cases(
    cases: Iterable[BenchmarkCase],
    settings: BenchmarkSettings,
    dataset: DatasetSpec,
) -> list[dict[str, object]]:
    """Time, validate, and normalize a group of already allocated cases."""
    rows: list[dict[str, object]] = []
    for case in cases:
        timing = _measure(
            case.invoke,
            warmup_iterations=settings.warmup_iterations,
            measured_iterations=settings.measured_iterations,
            target_sample_ms=settings.target_sample_ms,
        )
        valid, validation_error = case.validate()
        if not valid:
            raise RuntimeError(
                (
                    "Correctness validation failed for "
                    f"{case.operator}/{case.variant}: {validation_error}"
                )
            )
        median_seconds = timing["median_ns"] / 1_000_000_000
        rows.append(
            {
                "operator": case.operator,
                "variant": case.variant,
                "dtype": case.dtype,
                "shape": case.shape,
                "elements": case.elements,
                "input_bytes": case.input_bytes,
                "output_bytes": case.output_bytes,
                "logical_bytes_per_invocation": case.logical_bytes,
                "floating_point_operations_per_invocation": case.floating_point_operations,
                "warmup_iterations": settings.warmup_iterations,
                "measured_iterations": settings.measured_iterations,
                "inner_iterations": timing["inner_iterations"],
                "median_ms": _round(timing["median_ns"] / 1_000_000),
                "p50_ms": _round(timing["p50_ns"] / 1_000_000),
                "p95_ms": _round(timing["p95_ns"] / 1_000_000),
                "min_ms": _round(timing["min_ns"] / 1_000_000),
                "mean_ms": _round(timing["mean_ns"] / 1_000_000),
                "process_cpu_median_ms": _round(timing["process_cpu_median_ns"] / 1_000_000),
                "coefficient_of_variation": _round(timing["coefficient_of_variation"]),
                "effective_bandwidth_gb_s": _round(
                    case.logical_bytes / median_seconds / 1_000_000_000
                ),
                "estimated_gflop_s": _round(
                    case.floating_point_operations / median_seconds / 1_000_000_000
                ),
                "elements_per_second": _round(case.elements / median_seconds),
                "correctness_status": "passed",
                "dataset_seed": dataset.seed,
                "wall_time_ns_samples": timing["wall_time_ns_samples"],
                "process_cpu_time_ns_samples": timing["process_cpu_time_ns_samples"],
            }
        )
    return rows


def _measure(
    invoke: Callable[[], None],
    warmup_iterations: int,
    measured_iterations: int,
    target_sample_ms: float,
) -> dict[str, object]:
    """Measure an operator after warmup, with calibration for tiny workloads."""
    for _ in range(warmup_iterations):
        invoke()

    calibration_start = time.perf_counter_ns()
    invoke()
    calibration_ns = max(time.perf_counter_ns() - calibration_start, 1)
    target_ns = int(target_sample_ms * 1_000_000)
    inner_iterations = min(10_000, max(1, math.ceil(target_ns / calibration_ns)))

    wall_samples: list[float] = []
    cpu_samples: list[float] = []
    for _ in range(measured_iterations):
        wall_start = time.perf_counter_ns()
        cpu_start = time.process_time_ns()
        for _ in range(inner_iterations):
            invoke()
        cpu_elapsed = time.process_time_ns() - cpu_start
        wall_elapsed = time.perf_counter_ns() - wall_start
        wall_samples.append(wall_elapsed / inner_iterations)
        cpu_samples.append(cpu_elapsed / inner_iterations)

    mean_ns = statistics.fmean(wall_samples)
    return {
        "inner_iterations": inner_iterations,
        "wall_time_ns_samples": [_round(sample) for sample in wall_samples],
        "process_cpu_time_ns_samples": [_round(sample) for sample in cpu_samples],
        "min_ns": min(wall_samples),
        "median_ns": statistics.median(wall_samples),
        "p50_ns": _quantile(wall_samples, 0.50),
        "p95_ns": _quantile(wall_samples, 0.95),
        "mean_ns": mean_ns,
        "process_cpu_median_ns": statistics.median(cpu_samples),
        "coefficient_of_variation": (statistics.pstdev(wall_samples) / mean_ns if mean_ns else 0.0),
    }


def _create_result_directory(output_root: Path, experiment_name: str, config_path: Path) -> Path:
    """Create a unique run directory without overwriting another experiment."""
    root = output_root.resolve()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()[:8]
    safe_name = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in experiment_name
    )
    base_name = f"{timestamp}-{config_hash}"
    target_parent = root / safe_name
    target_parent.mkdir(parents=True, exist_ok=True)
    candidate = target_parent / base_name
    suffix = 1
    while candidate.exists():
        candidate = target_parent / f"{base_name}-{suffix:02d}"
        suffix += 1
    candidate.mkdir()
    return candidate


def _write_artifacts(
    result_directory: Path,
    rows: list[dict[str, object]],
    manifest: dict[str, object],
    settings: BenchmarkSettings,
) -> None:
    """Write machine-readable metrics plus exact configuration snapshots."""
    metrics_path = result_directory / "metrics.json"
    metrics_payload = {
        "schema_version": 1,
        "metric_unit_notes": {
            "effective_bandwidth_gb_s": (
                "logical read/write bytes divided by median wall time; not physical DDR bandwidth"
            ),
            "estimated_gflop_s": "declared floating point operations divided by median wall time",
        },
        "metrics": rows,
    }
    metrics_path.write_text(
        json.dumps(metrics_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (result_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(settings.config_path, result_directory / "config.toml")
    shutil.copy2(settings.dataset_path, result_directory / "dataset.toml")
    _write_csv(result_directory / "summary.csv", rows)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write a compact table; the JSON artifact retains per-sample timing."""
    fieldnames = [
        "operator",
        "variant",
        "dtype",
        "shape",
        "elements",
        "input_bytes",
        "output_bytes",
        "logical_bytes_per_invocation",
        "floating_point_operations_per_invocation",
        "warmup_iterations",
        "measured_iterations",
        "inner_iterations",
        "median_ms",
        "p50_ms",
        "p95_ms",
        "min_ms",
        "mean_ms",
        "process_cpu_median_ms",
        "coefficient_of_variation",
        "effective_bandwidth_gb_s",
        "estimated_gflop_s",
        "elements_per_second",
        "correctness_status",
        "dataset_seed",
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({field: row[field] for field in fieldnames} for row in rows)


def _build_manifest(
    numpy: Any,
    settings: BenchmarkSettings,
    dataset: DatasetSpec,
    result_directory: Path,
    started_at: datetime,
    finished_at: datetime,
) -> dict[str, object]:
    """Collect environment facts needed to interpret an experiment result."""
    return {
        "schema_version": 1,
        "status": "completed",
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "result_directory": str(result_directory),
        "command": sys.argv,
        "experiment": {
            "name": settings.experiment.name,
            "seed": settings.experiment.seed,
            "workload": settings.experiment.workload_name,
            "memory_type": settings.experiment.memory_type,
            "near_memory_enabled": settings.experiment.near_memory_enabled,
            "config_sha256": hashlib.sha256(settings.config_path.read_bytes()).hexdigest(),
        },
        "dataset": {
            **asdict(dataset),
            "fingerprint_sha256": _fingerprint_dataset(dataset),
            "path": str(settings.dataset_path),
        },
        "runtime": {
            "python_version": sys.version,
            "numpy_version": numpy.__version__,
            "platform": platform.platform(),
            "kernel_release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
            "cpu_affinity": _cpu_affinity(),
            "memory_bytes": _memory_bytes(),
            "numpy_build_configuration": _numpy_build_configuration(numpy),
            "thread_environment": {
                key: os.environ.get(key) for key in THREAD_ENVIRONMENT_VARIABLES
            },
        },
        "repository": _git_metadata(),
        "measurement_limitations": [
            "Wall time comes from time.perf_counter_ns().",
            "No cycles, instructions, cache-miss, frequency, or temperature counters are required.",
            "Effective bandwidth uses logical algorithm bytes and can include cache effects.",
            (
                "This result is a WSL/Linux process baseline and is not directly comparable "
                "to bare-metal or DPU timings."
            ),
        ],
    }


def _fingerprint_dataset(dataset: DatasetSpec) -> str:
    """Hash the generation contract, not the generated data inside timed runs."""
    payload = json.dumps(asdict(dataset), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _numpy_build_configuration(numpy: Any) -> str:
    """Capture the linked BLAS/LAPACK information without polluting benchmark output."""
    stream = io.StringIO()
    with (
        contextlib.redirect_stdout(stream),
        warnings.catch_warnings(),
    ):
        warnings.simplefilter("ignore", UserWarning)
        numpy.show_config()
    return stream.getvalue()


def _git_metadata() -> dict[str, object]:
    """Return best-effort repository provenance without making repository changes."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}
    return {"commit": commit, "dirty": dirty}


def _cpu_affinity() -> list[int] | None:
    """Return the process CPU affinity when the platform exposes it."""
    try:
        return sorted(os.sched_getaffinity(0))
    except AttributeError:
        return None


def _memory_bytes() -> dict[str, int] | None:
    """Read Linux memory availability when running inside Linux or WSL."""
    meminfo_path = Path("/proc/meminfo")
    if not meminfo_path.is_file():
        return None
    values: dict[str, int] = {}
    for line in meminfo_path.read_text(encoding="utf-8").splitlines():
        key, _, raw_value = line.partition(":")
        fields = raw_value.strip().split()
        if len(fields) < 2:
            continue
        number, unit, *_ = fields
        if unit == "kB" and key in {"MemTotal", "MemAvailable"}:
            values[key] = int(number) * 1024
    return {
        "total": values.get("MemTotal", 0),
        "available": values.get("MemAvailable", 0),
    }


def _resolve_output_root(experiment: ExperimentConfig) -> Path:
    """Anchor relative output paths at repository root rather than the caller CWD."""
    if experiment.output_directory.is_absolute():
        return experiment.output_directory
    return REPOSITORY_ROOT / experiment.output_directory


def _load_numpy() -> Any:
    """Import the optional CPU dependency only when a benchmark is requested."""
    try:
        import numpy
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "NumPy is required for the CPU benchmark. Install with: "
            "python -m pip install -e '.[cpu,dev]'"
        ) from error
    return numpy


def _rng(numpy: Any, seed: int) -> Any:
    """Create an explicitly named deterministic random generator."""
    return numpy.random.Generator(numpy.random.PCG64(seed))


def _load_toml(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("rb") as config_file:
        raw = tomllib.load(config_file)
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a TOML table at the root of {path}")
    return raw


def _mapping(raw: Mapping[str, object], key: str, path: Path) -> Mapping[str, object]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Expected [{key}] table in {path}")
    return value


def _required_string(section: Mapping[str, object], key: str, section_name: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{section_name}.{key} must be a non-empty string")
    return value


def _positive_int(section: Mapping[str, object], key: str, section_name: str) -> int:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{section_name}.{key} must be a positive integer")
    return value


def _non_negative_int(section: Mapping[str, object], key: str, section_name: str) -> int:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{section_name}.{key} must be a non-negative integer")
    return value


def _number(section: Mapping[str, object], key: str, section_name: str) -> float:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{section_name}.{key} must be a number")
    return float(value)


def _positive_number(section: Mapping[str, object], key: str, section_name: str) -> float:
    value = _number(section, key, section_name)
    if value <= 0:
        raise ValueError(f"{section_name}.{key} must be greater than zero")
    return value


def _positive_int_tuple(
    section: Mapping[str, object],
    key: str,
    section_name: str,
) -> tuple[int, ...]:
    value = section.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{section_name}.{key} must be a non-empty array")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise ValueError(f"{section_name}.{key} must contain positive integers")
    if len(set(value)) != len(value):
        raise ValueError(f"{section_name}.{key} must not contain duplicates")
    return tuple(value)


def _quantile(values: list[float], fraction: float) -> float:
    """Return a linearly interpolated quantile without adding another dependency."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _round(value: float) -> float:
    return round(value, 6)
