"""Run CPU configurations serially in fresh processes and retain run-level evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import uuid
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIGS = (
    "configs/cpu_server_285k_pcore.toml",
    "configs/cpu_server_285k_ecore.toml",
    "configs/cpu_server_285k_pcore_2t.toml",
    "configs/cpu_server_285k_pcore_4t.toml",
    "configs/cpu_server_285k_pcore_8t.toml",
)


class SummaryMetric(TypedDict):
    """Fields read from each benchmark metric when aggregating independent runs."""

    operator: str
    variant: str
    dtype: str
    shape: str
    median_ms: float
    coefficient_of_variation: float
    correctness_status: str


def command_output(arguments: list[str]) -> str:
    """Read command output without modifying Git or the Python environment."""
    return subprocess.run(
        arguments, cwd=REPOSITORY_ROOT, check=True, capture_output=True, text=True
    ).stdout


def configuration_order(configs: list[Path], round_index: int) -> list[Path]:
    """Rotate the first profile across rounds to reduce fixed-order effects."""
    offset = round_index % len(configs)
    return configs[offset:] + configs[:offset]


def summarize_runs(runs: list[dict[str, object]]) -> list[dict[str, object]]:
    """Summarize independent run medians, not pooled inner-loop samples."""
    groups: dict[tuple[str, ...], list[SummaryMetric]] = {}
    for run in runs:
        directory = Path(str(run["result_directory"]))
        metrics: dict[str, list[SummaryMetric]] = json.loads(
            (directory / "metrics.json").read_text(encoding="utf-8")
        )
        for row in metrics["metrics"]:
            if row["correctness_status"] != "passed":
                raise RuntimeError(f"Failed correctness check in {directory}")
            key = tuple(
                str(value)
                for value in (
                    run["profile"], row["operator"], row["variant"], row["dtype"], row["shape"]
                )
            )
            groups.setdefault(key, []).append(row)

    summary = []
    for (profile, operator, variant, dtype, shape), rows in sorted(groups.items()):
        values = [float(row["median_ms"]) for row in rows]
        mean = statistics.fmean(values)
        summary.append(
            {
                "profile": profile,
                "operator": operator,
                "variant": variant,
                "dtype": dtype,
                "shape": shape,
                "run_count": len(values),
                "median_of_run_medians_ms": statistics.median(values),
                "min_run_median_ms": min(values),
                "max_run_median_ms": max(values),
                "between_run_cv": statistics.pstdev(values) / mean if mean else 0.0,
                "median_within_run_cv": statistics.median(
                    float(row["coefficient_of_variation"]) for row in rows
                ),
                "correctness_status": "passed",
            }
        )
    return summary


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_sweep(configs: list[Path], rounds: int, output_root: Path) -> Path:
    """Persist provenance before testing and stop on the first failed child."""
    if rounds < 1:
        raise ValueError("rounds must be positive")
    if not configs:
        raise ValueError("at least one configuration is required")
    if len(set(configs)) != len(configs):
        raise ValueError("configuration paths must be unique")

    # Loading settings does not import NumPy. Each child configures threads before import.
    from pnm.benchmarks.cpu import THREAD_ENVIRONMENT_VARIABLES, load_benchmark_settings
    # 以文件路径为 key，索引对应的 benchmark 配置
    settings_by_path = {path: load_benchmark_settings(path) for path in configs}
    # 取出所有 setting 的 profiles
    profiles = [settings.execution_profile for settings in settings_by_path.values()]
    if None in profiles or len(set(profiles)) != len(profiles):
        raise ValueError("each configuration needs a unique execution.profile") # execution 是执行
    for settings in settings_by_path.values():
        if settings.cpu_affinity is None or settings.thread_count is None:
            raise ValueError("each configuration needs explicit affinity and thread controls")
        if settings.thread_count > len(settings.cpu_affinity):
            raise ValueError("thread_count must not exceed the number of selected CPUs")
        if not hasattr(os, "sched_getaffinity"): # sched_getaffinity 查询线程能在哪些 CPU 上运行
            raise RuntimeError("this CPU sweep requires Linux affinity support")
        # issubset：左边集合是不是全部包含在右边集合中
        if not set(settings.cpu_affinity).issubset(os.sched_getaffinity(0)):
            raise ValueError("a configuration requests CPUs outside the allowed affinity")
    # 生成随机 UUID（128 位随机数）转成 32 位小写十六进制字符串，只取前 8 个
    suite_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    directory = output_root / suite_id
    # 如果目标目录**已经存在**，直接抛异常 `FileExistsError`
    directory.mkdir(parents=True, exist_ok=False)
    tracked_paths = command_output(["git", "ls-files", "-z"]).split("\0")
    source_paths = {
        REPOSITORY_ROOT / name
        for name in tracked_paths
        if name and name.startswith(("src/", "scripts/", "configs/", "data/sample/"))
    }
    source_paths.update(configs)
    source_paths.add(Path(__file__).resolve())
    source_hashes = {
        str(path.relative_to(REPOSITORY_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source_paths)
        if path.is_file()
    }
    write_json(directory / "source_sha256.json", source_hashes)
    (directory / "working_tree.patch").write_text(
        command_output(["git", "diff", "HEAD", "--"]), encoding="utf-8"
    )
    # Save a restorable copy of benchmark inputs even when new files are untracked.
    for path in source_paths:
        if path.is_file():
            destination = directory / "source_snapshot" / path.relative_to(REPOSITORY_ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    (directory / "pip-freeze.txt").write_text(
        command_output([sys.executable, "-m", "pip", "freeze"]), encoding="utf-8"
    )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "status": "running",
        "started_at_utc": datetime.now(UTC).isoformat(),
        "rounds_requested": rounds,
        "configurations": [str(path.relative_to(REPOSITORY_ROOT)) for path in configs],
        "ordering": "serial, one-position cyclic rotation each round",
        "python_version": sys.version,
        "python_executable": sys.executable,
        "zlib_build_version": zlib.ZLIB_VERSION,
        "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
        "hostname": platform.node(),
        "repository_commit": command_output(["git", "rev-parse", "HEAD"]).strip(),
        "repository_status": command_output(["git", "status", "--porcelain"]),
        "runs": [],
        "limitations": [
            "Warm repeated-input tests; these are not cold-cache or storage-I/O tests.",
            "Thread settings do not parallelize every NumPy operator.",
            "Three independent runs are preliminary, not a confidence interval.",
            "Source snapshots preserve dirty inputs; they do not make Git clean.",
        ],
    }
    manifest_path = directory / "suite_manifest.json"
    write_json(manifest_path, manifest)
    print(f"CPU sweep artifacts: {directory}", flush=True)
    runs: list[dict[str, object]] = []
    try:
        for round_index in range(rounds):
            for config in configuration_order(configs, round_index):
                settings = settings_by_path[config]
                # 上面的配置检查已排除 None；在此明确告知类型检查器。
                assert settings.cpu_affinity is not None
                for name, expected in source_hashes.items():
                    current = REPOSITORY_ROOT / name
                    if (
                        not current.is_file()
                        or hashlib.sha256(current.read_bytes()).hexdigest() != expected
                    ):
                        raise RuntimeError(f"Source changed during sweep: {name}")
                profile = str(settings.execution_profile)
                job_root = directory / f"round-{round_index + 1:02d}" / profile
                job_root.mkdir(parents=True, exist_ok=False)
                load_before = list(os.getloadavg())
                print(f"Round {round_index + 1}/{rounds}: {profile}", flush=True)
                # The core module has no __main__ entry. Invoke its CLI explicitly.
                arguments = [
                    sys.executable,
                    "-c",
                    "from pnm.benchmarks.cpu import main; raise SystemExit(main())",
                    "--config",
                    str(config),
                    "--output-dir",
                    str(job_root),
                ]
                with (job_root / "process.log").open("w", encoding="utf-8") as log:
                    subprocess.run(
                        arguments, cwd=REPOSITORY_ROOT, stdout=log, stderr=log, check=True
                    )
                children = list(job_root.glob("*/*/manifest.json"))
                if len(children) != 1:
                    raise RuntimeError(f"Expected one result bundle in {job_root}")
                child_manifest = json.loads(children[0].read_text(encoding="utf-8"))
                if child_manifest["runtime"]["cpu_affinity"] != list(settings.cpu_affinity):
                    raise RuntimeError(f"Affinity mismatch in {job_root}")
                thread_environment = child_manifest["runtime"]["thread_environment"]
                if any(
                    thread_environment.get(variable) != str(settings.thread_count)
                    for variable in THREAD_ENVIRONMENT_VARIABLES
                ):
                    raise RuntimeError(f"Thread environment mismatch in {job_root}")
                metrics = json.loads(
                    (children[0].parent / "metrics.json").read_text(encoding="utf-8")
                )["metrics"]
                if not metrics or any(row["correctness_status"] != "passed" for row in metrics):
                    raise RuntimeError(f"Correctness validation failed in {job_root}")
                runs.append(
                    {
                        "round": round_index + 1,
                        "profile": profile,
                        "result_directory": str(children[0].parent),
                        "case_count": len(metrics),
                        "load_before": load_before,
                        "load_after": list(os.getloadavg()),
                    }
                )
                manifest["runs"] = runs
                write_json(manifest_path, manifest)
        write_json(directory / "aggregate.json", {"metrics": summarize_runs(runs)})
        manifest["status"] = "completed"
    except BaseException as error:
        manifest["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        manifest["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        manifest["finished_at_utc"] = datetime.now(UTC).isoformat()
        write_json(manifest_path, manifest)
    print(f"CPU sweep completed: {directory}", flush=True)
    return directory


def main() -> int:
    parser = argparse.ArgumentParser(description = __doc__) # 初始化 ArgumentParser
    # nargs = "+" 接收 ≥1 个参数，收集成列表
    parser.add_argument("--configs", nargs = "+", default = list(DEFAULT_CONFIGS), type = Path)
    parser.add_argument("--rounds", type = int, default = 3)
    parser.add_argument("--output-dir", type = Path, default = Path("outputs/server-285k-sweeps"))
    args = parser.parse_args() # 解析命令行传入的参数，得到 args 对象
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    # 获取 configs 的绝对路径
    configs = [(REPOSITORY_ROOT / path).resolve() for path in args.configs]
    # .resolve 把路径转换成完整、标准化的绝对路径
    run_sweep(configs, args.rounds, (REPOSITORY_ROOT / args.output_dir).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
