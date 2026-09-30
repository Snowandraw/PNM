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

REPOSITORY_ROOT = Path(__file__).resolve().parents[3] # 仓库的根目录
SUPPORTED_OPERATORS = frozenset( # 冻结的算子集合
    {
        "copy", # 内存搬运型
        "add", # 简单计算型
        "multiply", # 简单计算型
        "relu", # 简单计算型
        "sum", # 简单计算型
        "gather", # 内存搬运型
        "transpose_copy", # 内存搬运型
        "threshold_count", # 数据处理型
        "filter_compact", # 数据处理型
        "histogram", # 数据处理型
        "crc32", # 网络 / 数据处理型
        "matmul", # 数据处理型
    }
)
THREAD_ENVIRONMENT_VARIABLES = ( # 环境变量专门用来控制底层数值计算库的线程数
    "OPENBLAS_NUM_THREADS", # 控制 OpenBLAS 线性代数库的线程数。Linux / WSL 下 Numpy 最常见的后端就是 OpenBLAS
    "OMP_NUM_THREADS", # 控制所有 OpenMP 并行代码（很多 C++ 算子、PyTorch、SciPy）的线程数
    "MKL_NUM_THREADS", # 英特尔数学内核库；Windows 版 Numpy、Anaconda 默认后端
    "BLIS_NUM_THREADS", # 高性能 BLAS 库，部分 ARM/AMD 平台 numpy 会选用
    "NUMEXPR_NUM_THREADS", # numpy 加速库，用于数组运算多线程
)


@dataclass(frozen = True)
class DatasetSpec: # 数据集的配置说明书
    """Description of deterministic inputs generated at runtime."""

    schema_version: int # 配置文件版本号，后续改结构体字段时做向前兼容
    name: str # 数据集名字
    seed: int # 固定种子，随机生成的数据每次都一样，消除实验随机性
    dtype: str # 数据类型
    generator: str # 生成器名字
    vector_sizes: tuple[int, ...] # 不定长 int 元组一维向量的尺寸列表，用来跑向量算子
    matrix_sizes: tuple[int, ...] # 不定长 int 元组矩阵长宽尺寸列表，`matmul`矩阵乘法用
    record_counts: tuple[int, ...] # 元素条数，`gather`、`histogram`这类算子需要的样本数量
    histogram_bins: int # 直方图算子的分桶数量
    filter_threshold: float # 阈值
    payload_sizes: tuple[int, ...] # 不定长 int 元组负载数据字节大小，给 CRC32 等数据校验算子使用


@dataclass(frozen = True)
class BenchmarkSettings:
    """CPU benchmark options loaded from an experiment configuration."""

    experiment: ExperimentConfig # 自定义类嵌套引用顶层实验配置对象，包含数据集规格 DatasetSpec 等全部实验参数
    config_path: Path # .toml 实验配置文件所在的完整路径，方便日志输出、溯源配置文件
    dataset_path: Path # 生成出来的测试数据集，保存到磁盘的文件夹路径
    warmup_iterations: int # 预热迭代次数
    measured_iterations: int # 正式测量迭代次数
    target_sample_ms: float # 目标单次采样时长
    operators: tuple[str, ...] # 本次要跑的算子名称元组


@dataclass
class BenchmarkCase: # 
    """One allocated data shape and one timed operator."""
    # 一个已经分配好的数据形状 + 一个待计时运行的算子，代表一次独立的跑分用例
    operator: str # 算子名称
    variant: str # 算子变体如："cpu‑numpy"、"dpu‑offload"
    shape: str # 张量形状，例如 `"2048×2048"`，用于日志打印
    dtype: str # 数据类型，`"float32"` / `"int32"`
    elements: int # 张量总元素数量，2048*2048 = 4,194,304
    input_bytes: int # 输入数据所占内存字节大小
    output_bytes: int # 输出结果所占内存字节大小
    logical_bytes: int # 逻辑访存字节数，理论上算子读写的数据总量，用来计算带宽
    floating_point_operations: int # FLOPs，浮点运算总次数，用来计算算力 GFLOPS
    invoke: Callable[[], None] # 真正要跑、计时的算子函数
    validate: Callable[[], tuple[bool, str | None]] # 结果校验函数


def build_parser() -> argparse.ArgumentParser: # 创建并返回一个命令行解析对象
    # 给 CPU benchmark 定义一个命令行入口规范：配置文件从哪里来，结果输出到哪里去。
    """Create the dedicated CPU benchmark CLI parser."""
    parser = argparse.ArgumentParser(
        # 运行可复现的NumPy CPU算子基线。
        description = "Run the reproducible NumPy CPU operator baseline."
    )
    parser.add_argument(
        "--config",
        type = Path,
        required = True,
        # 带有 [cpu_benchmark] 部分的 TOML 实验配置路径
        help = "Path to a TOML experiment configuration with a [cpu_benchmark] section.",
    )
    parser.add_argument(
        "--output-dir",
        type = Path,
        # 可选输出根目录。默认为配置文件中的[output].directory。
        help = "Optional output root. Defaults to [output].directory in the configuration.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run a CPU benchmark and print its artifact directory."""
    args = build_parser().parse_args(argv) # 解析输入参数
    # 如果 bash 里面没写 --output-dir 那么这里传入的 args.output_dir 是 None
    output_path = run_benchmark(args.config, output_root = args.output_dir)
    print(f"CPU benchmark completed: {output_path}")
    return 0


def run_benchmark(config_path: Path, output_root: Path | None = None) -> Path:
    # 运行所有已选中的 CPU 测试用例，并将结果保存为一个自带描述信息的结果包。
    """Run all selected CPU cases and persist a self-describing result bundle."""
    numpy = _load_numpy()
    # 分别把 cpu_baseline.toml 和 cpu_operator_suite.toml 的信息加载进 settings 和 dataset
    settings = load_benchmark_settings(config_path) # 获取 BenchmarkSettings 数据
    dataset = load_dataset_spec(settings.dataset_path) # 传入数据集的路径获取具体的 DatasetSpec 数据集信息
    selected_operators = frozenset(settings.operators) # 把元组转 frozenset
    started_at = datetime.now(UTC) # 获取执行到这一行时的 UTC 时间，保存为实验开始时间
    # 创建一个空列表 rows，准备存放多条测试结果，每条结果用一个字典表示。
    rows: list[dict[str, object]] = []
    # 遍历每一种向量长度，创建对应的测试用例、运行测试，再把结果加入 rows
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

    finished_at = datetime.now(UTC) # 获取执行到这一行时的 UTC 时间，保存为实验结束时间 
    result_directory = _create_result_directory( # 执行一次创建一个 result_directory 类似 20260825T095442Z-7530fdc3
        output_root or _resolve_output_root(settings.experiment), # 第一个参数是路径
        settings.experiment.name,
        settings.config_path, # cpu_baseline.toml
    )
    manifest = _build_manifest(
        numpy = numpy,
        settings = settings, # BenchmarkSettings 里面的信息
        dataset = dataset, # DatasetSpec 里面的信息
        result_directory = result_directory, # 最后存入的文件夹路径
        started_at = started_at, # 传入实验开始的时间
        finished_at = finished_at, # 传入实验结束的时间
    )
    _write_artifacts(result_directory, rows, manifest, settings)
    return result_directory


def load_benchmark_settings(config_path: Path) -> BenchmarkSettings:
    # 加载基础实验配置，并附加 CPU 专用配置片段。
    """Load the base experiment config plus the CPU-specific section."""
    resolved_config_path = config_path.resolve() # 把传入的路径转换成绝对路径 configs/cpu_baseline.toml -> /home/snow/PNM/configs/cpu_baseline.toml
    experiment = load_experiment_config(resolved_config_path) # 加载实验配置，返回 ExperimentConfig 类型记录了 cpu_baseline 中详细的属性值
    raw = _load_toml(resolved_config_path) # 传入绝对路径获取 cpu_baseline 中的配置信息记为字典 raw
    section = _mapping(raw, "cpu_benchmark", resolved_config_path) # 取出这个 cpu_benchmark 所对应的信息，转为 dict
    dataset_value = _required_string(section, "dataset", "cpu_benchmark") # 拿出 cpu_benchmark 中 dataset 所对应的值
    dataset_path = Path(dataset_value)
    if not dataset_path.is_absolute(): # 如果不是绝对路径就把它拼接到仓库根目录下
        dataset_path = REPOSITORY_ROOT / dataset_path
    # dataset_path 变成真正的绝对路径
    operators_value = section.get("operators")
    if not isinstance(operators_value, list) or not operators_value: # 是非空的列表
        raise ValueError("cpu_benchmark.operators must be a non-empty TOML array")
    operators = tuple(operators_value) # 把列表转换成元组
    # 只要有任意一个不是 string 就报错
    if any(not isinstance(operator, str) for operator in operators):
        raise ValueError("cpu_benchmark.operators must contain only strings")
    unknown_operators = sorted(set(operators) - SUPPORTED_OPERATORS) # 按字典序从小到大得到不受支持的算子集合
    if unknown_operators:
        raise ValueError(f"Unsupported CPU operators: {', '.join(unknown_operators)}")
    # 不能有重复的
    if len(set(operators)) != len(operators):
        raise ValueError("cpu_benchmark.operators must not contain duplicates")

    return BenchmarkSettings(
        experiment = experiment, # cpu_baseline 中的参数信息
        config_path = resolved_config_path, # 绝对路径
        dataset_path = dataset_path.resolve(), # 数据集规模的路径，按照 bash 中 cd 到的路径进行拼接规格化
        warmup_iterations = _non_negative_int(section, "warmup_iterations", "cpu_benchmark"), # 获取预热次数 >= 0
        measured_iterations = _positive_int(section, "measured_iterations", "cpu_benchmark"), # 获取测量迭代次数 > 0
        target_sample_ms = _positive_number(section, "target_sample_ms", "cpu_benchmark"), # 获取目标采样毫秒数
        operators = operators, # 获取算子集
    )


def load_dataset_spec(path: Path) -> DatasetSpec:
    """Load and validate the data shapes used by the synthetic input generator."""
    # 加载并校验合成输入生成器所使用的数据维度。
    resolved_path = path.resolve() # 获取绝对路径
    raw = _load_toml(resolved_path)
    dataset = _mapping(raw, "dataset", resolved_path)
    vector = _mapping(raw, "vector", resolved_path)
    matrix = _mapping(raw, "matrix", resolved_path)
    records = _mapping(raw, "records", resolved_path)
    payload = _mapping(raw, "payload", resolved_path)

    dtype = _required_string(dataset, "dtype", "dataset") # 获取 cpu_operator_suite/dataset 下 dtype 的值 
    if dtype != "float32":
        raise ValueError("dataset.dtype must currently be 'float32'")

    return DatasetSpec(
        schema_version = _positive_int(dataset, "schema_version", "dataset"),
        name = _required_string(dataset, "name", "dataset"),
        seed = _non_negative_int(dataset, "seed", "dataset"),
        dtype = dtype,
        generator = _required_string(dataset, "generator", "dataset"),
        vector_sizes = _positive_int_tuple(vector, "sizes", "vector"),
        matrix_sizes = _positive_int_tuple(matrix, "sizes", "matrix"),
        record_counts = _positive_int_tuple(records, "counts", "records"),
        histogram_bins = _positive_int(records, "histogram_bins", "records"),
        filter_threshold = _number(records, "filter_threshold", "records"),
        payload_sizes = _positive_int_tuple(payload, "sizes", "payload"),
    )


def _vector_cases(numpy: Any, dataset: DatasetSpec, selected: frozenset[str], elements: int) -> list[BenchmarkCase]:
    # 构建向量测试用例，同一时刻仅保留一组工作集处于活跃状态。
    """Build vector cases while keeping one working set alive at a time."""
    # active 为 selected 和后者的交集
    active = selected & {"copy", "add", "multiply", "relu", "sum", "gather"}
    # 如果一个向量算子都没选，就直接返回空列表，不再准备数据。
    if not active:
        return []

    generator = _rng(numpy, dataset.seed + elements) # 生成一个根据指定 seed 的生成器
    left = generator.standard_normal(elements, dtype = numpy.float32) # 生成 elements 个服从标准正态分布的随机数
    right = generator.standard_normal(elements, dtype = numpy.float32) # 生成 elements 个服从标准正态分布的随机数
    output = numpy.empty_like(left) # 创建一个与 left 形状、数据类型相同的新数组，但不初始化其中的数值
    itemsize = left.itemsize # 获取 left 数组中每个元素占用的字节数，保存到变量 itemsize
    cases: list[BenchmarkCase] = [] # : list[BenchmarkCase] 是类型注释

    if "copy" in active:

        def invoke_copy() -> None:
            numpy.copyto(output, left)

        def validate_copy() -> tuple[bool, str | None]:
            return bool(numpy.array_equal(output, left)), "copy output differs from input"

        cases.append(
            BenchmarkCase(
                operator = "copy",
                variant = "contiguous-f32",
                shape = str(elements),
                dtype = dataset.dtype,
                elements = elements,
                input_bytes = left.nbytes,
                output_bytes = output.nbytes,
                logical_bytes = 2 * elements * itemsize,
                floating_point_operations = 0,
                invoke = invoke_copy,
                validate = validate_copy,
            )
        )

    if "add" in active:

        def invoke_add() -> None:
            numpy.add(left, right, out = output) # 把 left 和 right 中对应位置的元素相加，将结果写入 output

        def validate_add() -> tuple[bool, str | None]:
            valid = numpy.allclose(output, left + right, rtol = 1e-6, atol = 1e-6) # 验证误差是否能接受，误差不大就是 True, 反之是 False
            return bool(valid), "add output failed validation"

        cases.append(
            BenchmarkCase(
                operator = "add",
                variant = "contiguous-f32",
                shape = str(elements),
                dtype = dataset.dtype,
                elements = elements,
                input_bytes = left.nbytes + right.nbytes,
                output_bytes = output.nbytes,
                logical_bytes = 3 * elements * itemsize, # 两次读和一次写
                floating_point_operations = elements, # 进行了 n 次加法
                invoke = invoke_add,
                validate = validate_add,
            )
        )

    if "multiply" in active:

        def invoke_multiply() -> None:
            numpy.multiply(left, right, out = output) # 将两个数组中对应位置的元素相乘，把结果写入 output

        def validate_multiply() -> tuple[bool, str | None]:
            valid = numpy.allclose(output, left * right, rtol = 1e-6, atol = 1e-6)
            return bool(valid), "multiply output failed validation"

        cases.append(
            BenchmarkCase(
                operator = "multiply",
                variant = "contiguous-f32",
                shape = str(elements),
                dtype = dataset.dtype,
                elements = elements,
                input_bytes = left.nbytes + right.nbytes,
                output_bytes = output.nbytes,
                logical_bytes = 3 * elements * itemsize,
                floating_point_operations = elements, # 两个向量相乘所以是 elements
                invoke = invoke_multiply,
                validate = validate_multiply,
            )
        )

    if "relu" in active:

        def invoke_relu() -> None:
            numpy.maximum(left, 0.0, out = output) # 会对 left 的每个元素与 0 取较大值

        def validate_relu() -> tuple[bool, str | None]:
            valid = numpy.allclose(output, numpy.maximum(left, 0.0), rtol = 0.0, atol = 0.0) # 检查 output 是否正确执行了 ReLU，并且不允许数值误差
            return bool(valid), "relu output failed validation"

        cases.append(
            BenchmarkCase(
                operator = "relu",
                variant = "contiguous-f32",
                shape = str(elements),
                dtype = dataset.dtype,
                elements = elements,
                input_bytes = left.nbytes,
                output_bytes = output.nbytes,
                logical_bytes = 2 * elements * itemsize,
                floating_point_operations = elements,
                invoke = invoke_relu,
                validate = validate_relu,
            )
        )

    if "sum" in active:
        expected_sum = float(numpy.sum(left, dtype = numpy.float32))
        sum_result = [0.0]

        def invoke_sum() -> None:
            sum_result[0] = float(numpy.sum(left, dtype = numpy.float32))

        def validate_sum() -> tuple[bool, str | None]:
            valid = math.isclose(sum_result[0], expected_sum, rel_tol = 1e-6, abs_tol = 1e-6)
            return valid, "sum output failed validation"

        cases.append(
            BenchmarkCase(
                operator = "sum",
                variant = "contiguous-f32",
                shape = str(elements),
                dtype = dataset.dtype,
                elements = elements,
                input_bytes = left.nbytes,
                output_bytes = itemsize,
                logical_bytes = left.nbytes + itemsize,
                floating_point_operations = max(elements - 1, 0),
                invoke = invoke_sum,
                validate = validate_sum,
            )
        )

    if "gather" in active:
        # 根据一组索引，从输入数组中取出对应元素，写入输出数组
        indices = generator.integers(0, elements, size = elements, dtype = numpy.intp) # 生成 elements 个 intp 数据类型 0 ~ elements - 1 范围的数
        def invoke_gather() -> None:
            numpy.take(left, indices, out = output) # 按 indices 指定的位置，从 left 取值，写入 output， output[i] = left[indices[i]]

        def validate_gather() -> tuple[bool, str | None]:
            return bool(numpy.array_equal(output, left[indices])), "gather output failed validation"
        # left 是 NumPy 数组，它支持用整数数组作为索引
        cases.append(
            BenchmarkCase(
                operator = "gather",
                variant = "random-index-f32",
                shape = str(elements),
                dtype = dataset.dtype,
                elements = elements,
                input_bytes = left.nbytes + indices.nbytes,
                output_bytes = output.nbytes,
                logical_bytes = left.nbytes + indices.nbytes + output.nbytes,
                floating_point_operations = 0,
                invoke = invoke_gather,
                validate = validate_gather,
            )
        )

    return cases


def _matrix_cases(numpy: Any, dataset: DatasetSpec, selected: frozenset[str], side: int) -> list[BenchmarkCase]:
    """Build layout-conversion and dense-linear-algebra cases."""
    active = selected & {"transpose_copy", "matmul"} # 转置复制和矩阵乘法
    if not active:
        return []

    generator = _rng(numpy, dataset.seed + (side << 8))
    source = generator.standard_normal((side, side), dtype = numpy.float32)
    output = numpy.empty_like(source)
    cases: list[BenchmarkCase] = []
    shape = f"({side}, {side})"

    if "transpose_copy" in active:

        def invoke_transpose() -> None:
            numpy.copyto(output, source.T) # 把 source 的转置写入 output 数组

        def validate_transpose() -> tuple[bool, str | None]:
            return bool(numpy.array_equal(output, source.T)), "transpose output failed validation"

        cases.append(
            BenchmarkCase(
                operator = "transpose_copy",
                variant = "materialized-f32",
                shape = shape,
                dtype = dataset.dtype,
                elements = source.size,
                input_bytes = source.nbytes,
                output_bytes = output.nbytes,
                logical_bytes = source.nbytes + output.nbytes,
                floating_point_operations = 0,
                invoke = invoke_transpose,
                validate = validate_transpose,
            )
        )

    if "matmul" in active:
        right = generator.standard_normal((side, side), dtype = numpy.float32)
        product = numpy.empty_like(source)

        def invoke_matmul() -> None:
            numpy.matmul(source, right, out = product)

        def validate_matmul() -> tuple[bool, str | None ]:
            return bool(numpy.isfinite(product).all()), "matmul produced a non-finite result"

        cases.append(
            BenchmarkCase(
                operator = "matmul",
                variant = "square-f32",
                shape = shape,
                dtype = dataset.dtype,
                elements = source.size,
                input_bytes = source.nbytes + right.nbytes,
                output_bytes = product.nbytes,
                logical_bytes = source.nbytes + right.nbytes + product.nbytes,
                floating_point_operations = 2 * side * side * side, # 每一个 output 元素需要进行 2 * n - 1 次计算
                invoke = invoke_matmul,
                validate = validate_matmul,
            )
        )

    return cases


def _record_cases(numpy: Any, dataset: DatasetSpec, selected: frozenset[str], count: int) -> list[BenchmarkCase]:
    """Build 16-byte-record filtering and aggregation cases."""
    active = selected & {"threshold_count", "filter_compact", "histogram"}
    if not active:
        return []

    record_dtype = numpy.dtype( # 每个元组的格式都是: ("字段名", "类型编码")
        [
            ("flow_id", "<u4"),
            ("timestamp", "<u4"),
            ("length", "<u2"),
            ("flags", "<u2"),
            ("value", "<f4"),
        ]
    )
    generator = _rng(numpy, dataset.seed + (count << 2)) # 创建生成器
    records = numpy.empty(count, dtype = record_dtype)
    records["flow_id"] = generator.integers( # 0 ～ histogram_bins-1 的随机整数
        0, dataset.histogram_bins, size = count, dtype = numpy.uint32
    )
    records["timestamp"] = numpy.arange(count, dtype = numpy.uint32) # 0、1、2 …… count - 1，作为模拟编号
    records["length"] = generator.integers(64, 1501, size = count, dtype = numpy.uint16) # 64 ～ 1500 的随机整数
    records["flags"] = generator.integers(0, 256, size = count, dtype = numpy.uint16) # 0 ～ 255 的随机整数
    records["value"] = generator.standard_normal(count, dtype = numpy.float32) # 标准正态分布随机数，有正有负

    flow_ids = records["flow_id"]
    values = records["value"]
    mask = numpy.empty(count, dtype = numpy.bool_) # 创建一个长度为 count 的布尔数组，准备存放每条记录是否满足筛选条件的标记
    expected_selected = int(numpy.count_nonzero(values > dataset.filter_threshold)) # 提前统计有多少条记录的 value 大于阈值，保存为后面校验用的预期数量
    cases: list[BenchmarkCase] = []

    if "threshold_count" in active: # 阈值计数的算子
        selected_count = [0]

        def invoke_threshold_count() -> None:
            numpy.greater(values, dataset.filter_threshold, out = mask) # 第一行逐元素判断是否超过阈值，把布尔结果写入预先分配的 mask
            selected_count[0] = int(numpy.count_nonzero(mask)) # 统计 True 的数量

        def validate_threshold_count() -> tuple[bool, str | None]:
            valid = selected_count[0] == expected_selected
            return valid, "threshold_count result failed validation"

        cases.append(
            BenchmarkCase(
                operator = "threshold_count",
                variant = "records-v1",
                shape = str(count),
                dtype = "records-v1",
                elements = count,
                input_bytes = values.nbytes,
                output_bytes = mask.nbytes + 8, # + 8 是因为 selected_count[0]
                logical_bytes = values.nbytes + 2 * mask.nbytes + 8, # 写一次 mask 读一次 mask
                floating_point_operations = count,
                invoke = invoke_threshold_count,
                validate = validate_threshold_count,
            )
        )

    if "filter_compact" in active:
        compacted = [numpy.empty(0, dtype = record_dtype)]

        def invoke_filter_compact() -> None:
            numpy.greater(values, dataset.filter_threshold, out = mask)
            compacted[0] = records[mask] # 将 True 的部分选出重新创建一个数组

        def validate_filter_compact() -> tuple[bool, str | None]:
            valid = compacted[0].size == expected_selected
            if valid and compacted[0].size:
                valid = bool(numpy.all(compacted[0]["value"] > dataset.filter_threshold))
            return valid, "filter_compact result failed validation"

        cases.append(
            BenchmarkCase(
                operator = "filter_compact",
                variant = "records-v1",
                shape = str(count),
                dtype = "records-v1",
                elements = count,
                input_bytes = records.nbytes,
                output_bytes = expected_selected * record_dtype.itemsize,
                logical_bytes = records.nbytes
                + 2 * mask.nbytes
                + expected_selected * record_dtype.itemsize,
                floating_point_operations = count,
                invoke = invoke_filter_compact,
                validate = validate_filter_compact,
            )
        )

    if "histogram" in active:
        histogram = [numpy.empty(0, dtype = numpy.int64)]

        def invoke_histogram() -> None:
            histogram[0] = numpy.bincount(flow_ids, minlength = dataset.histogram_bins) # 最小长度是 histogram_bins，统计每个数出现了几次转为数组存储在 histogram[0] 里面

        def validate_histogram() -> tuple[bool, str | None]:
            valid = histogram[0].size == dataset.histogram_bins
            if valid:
                valid = int(numpy.sum(histogram[0])) == count
            return valid, "histogram result failed validation"

        cases.append(
            BenchmarkCase(
                operator = "histogram",
                variant = f"records-v1-{dataset.histogram_bins}-bins",
                shape = str(count),
                dtype = "records-v1",
                elements = count,
                input_bytes = flow_ids.nbytes,
                output_bytes = dataset.histogram_bins * numpy.dtype(numpy.int64).itemsize, # histogram[0] 的大小
                logical_bytes = flow_ids.nbytes
                + dataset.histogram_bins * numpy.dtype(numpy.int64).itemsize,
                floating_point_operations = 0,
                invoke = invoke_histogram,
                validate = validate_histogram,
            )
        )

    return cases


def _payload_cases(numpy: Any, dataset: DatasetSpec, selected: frozenset[str], size: int) -> list[BenchmarkCase]:
    """Build checksum cases over deterministic high-entropy byte buffers."""
    if "crc32" not in selected:
        return []

    generator = _rng(numpy, dataset.seed + (size << 1))
    payload = generator.integers(0, 256, size = size, dtype = numpy.uint8) # 无符号的 1 字节
    payload_view = memoryview(payload) # memoryview 保存了底层缓冲区的内存起始地址 + 有效长度、偏移
    expected_crc = zlib.crc32(payload_view)  # 返回的是有符号 32 位整数
    crc_result = [0]

    def invoke_crc32() -> None:
        crc_result[0] = zlib.crc32(payload_view)

    def validate_crc32() -> tuple[bool, str | None]:
        return crc_result[0] == expected_crc, "crc32 result failed validation"

    return [
        BenchmarkCase(
            operator = "crc32",
            variant = "high-entropy-u8",
            shape = str(size),
            dtype = "uint8",
            elements = size,
            input_bytes = payload.nbytes,
            output_bytes = 4,
            logical_bytes = payload.nbytes + 4,
            floating_point_operations = 0,
            invoke = invoke_crc32,
            validate = validate_crc32,
        )
    ]


def _run_cases(cases: Iterable[BenchmarkCase], settings: BenchmarkSettings, dataset: DatasetSpec) -> list[dict[str, object]]:
    """Time, validate, and normalize a group of already allocated cases."""
    # 对一组已分配的案例进行时间处理、校验与标准化
    rows: list[dict[str, object]] = []
    for case in cases:
        timing = _measure(
            case.invoke,
            warmup_iterations = settings.warmup_iterations,
            measured_iterations = settings.measured_iterations,
            target_sample_ms = settings.target_sample_ms,
        )
        valid, validation_error = case.validate()
        if not valid:
            raise RuntimeError(
                (
                    "Correctness validation failed for "
                    f"{case.operator}/{case.variant}: {validation_error}"
                )
            )
        median_seconds = timing["median_ns"] / 1_000_000_000 # 纳秒换成秒
        rows.append( # 相当于 case 和 timing 里面的信息组合起来
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
                "median_ms": _round(timing["median_ns"] / 1_000_000), # 纳秒转换为毫秒，最多保留 6 位小数
                "p50_ms": _round(timing["p50_ns"] / 1_000_000),
                "p95_ms": _round(timing["p95_ns"] / 1_000_000),
                "min_ms": _round(timing["min_ns"] / 1_000_000),
                "mean_ms": _round(timing["mean_ns"] / 1_000_000),
                "process_cpu_median_ms": _round(timing["process_cpu_median_ns"] / 1_000_000),
                "coefficient_of_variation": _round(timing["coefficient_of_variation"]),
                "effective_bandwidth_gb_s": _round(
                    case.logical_bytes / median_seconds / 1_000_000_000 # 单位是 GB / s
                ),
                "estimated_gflop_s": _round(
                    case.floating_point_operations / median_seconds / 1_000_000_000 # GFLOP / s
                ),
                "elements_per_second": _round(case.elements / median_seconds),
                "correctness_status": "passed",
                "dataset_seed": dataset.seed,
                "wall_time_ns_samples": timing["wall_time_ns_samples"],
                "process_cpu_time_ns_samples": timing["process_cpu_time_ns_samples"],
            }
        )
    return rows


def _measure(invoke: Callable[[], None], warmup_iterations: int, measured_iterations: int, target_sample_ms: float) -> dict[str, object]:
    # 预热后对算子进行测量，并针对极小负载做校准。
    """Measure an operator after warmup, with calibration for tiny workloads."""
    for _ in range(warmup_iterations):
        invoke() # 用于减小首次执行、缓存状态等因素的影响

    calibration_start = time.perf_counter_ns() # 读取用于测量时间间隔的高精度时钟，返回值单位是纳秒。
    invoke()
    calibration_ns = max(time.perf_counter_ns() - calibration_start, 1)
    target_ns = int(target_sample_ms * 1_000_000)
    inner_iterations = min(10_000, max(1, math.ceil(target_ns / calibration_ns))) # 每组执行次数 ≈ 目标采样时长 ÷ 单次运行耗时

    wall_samples: list[float] = []
    cpu_samples: list[float] = []
    for _ in range(measured_iterations):
        # 正式采样：每组运行多次，再计算平均单次耗时
        wall_start = time.perf_counter_ns()
        cpu_start = time.process_time_ns()
        for _ in range(inner_iterations):
            invoke()
        cpu_elapsed = time.process_time_ns() - cpu_start
        wall_elapsed = time.perf_counter_ns() - wall_start
        wall_samples.append(wall_elapsed / inner_iterations)
        cpu_samples.append(cpu_elapsed / inner_iterations)

    mean_ns = statistics.fmean(wall_samples) # 计算这些采样值的平均数
    return {
        "inner_iterations": inner_iterations,
        "wall_time_ns_samples": [_round(sample) for sample in wall_samples], # 把每个采样值舍入到小数点后 6 位，再组成新列表
        "process_cpu_time_ns_samples": [_round(sample) for sample in cpu_samples], # 把每个采样值舍入到小数点后 6 位，再组成新列表
        "min_ns": min(wall_samples),
        "median_ns": statistics.median(wall_samples),
        "p50_ns": _quantile(wall_samples, 0.50),
        "p95_ns": _quantile(wall_samples, 0.95),
        "mean_ns": mean_ns,
        "process_cpu_median_ns": statistics.median(cpu_samples),
        "coefficient_of_variation": (statistics.pstdev(wall_samples) / mean_ns if mean_ns else 0.0), # 变异系数（CV），用来衡量采样耗时的相对波动程度
    }


def _create_result_directory(output_root: Path, experiment_name: str, config_path: Path) -> Path: # 创建一组用于存放实验数据的 dir 并且返回该 dir 的路径
    """Create a unique run directory without overwriting another experiment."""
    root = output_root.resolve() # 取出绝对路径这里放的是 output 的路径
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") # 获取当前 UTC 时间，并把它格式化成适合放进目录名的字符串
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()[:8] # 以字节形式读取配置文件的全部内容然后根据文件内容计算 SHA-256 哈希，将哈希转换成一个长度为 64 的十六进制字符串，最后通过切片取前 8 个字符，哈希的主要目的不是防止重名是为了标识使用了哪一版配置文件
    safe_name = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in experiment_name # cpu-baseline-7840h-wsl
    )
    base_name = f"{timestamp}-{config_hash}" # 20260825T095442Z-7530fdc3 的由来
    target_parent = root / safe_name
    target_parent.mkdir(parents = True, exist_ok = True)
    candidate = target_parent / base_name
    suffix = 1
    while candidate.exists():
        candidate = target_parent / f"{base_name}-{suffix:02d}"
        suffix += 1
    candidate.mkdir()
    return candidate


def _write_artifacts(result_directory: Path, rows: list[dict[str, object]], manifest: dict[str, object], settings: BenchmarkSettings) -> None:
    """Write machine-readable metrics plus exact configuration snapshots."""
    metrics_path = result_directory / "metrics.json"
    metrics_payload = {
        "schema_version": 1, # 格式版本号 
        "metric_unit_notes": { # 指标说明注释
            "effective_bandwidth_gb_s": (
                "logical read/write bytes divided by median wall time; not physical DDR bandwidth"
            ),
            "estimated_gflop_s": "declared floating point operations divided by median wall time",
        },
        "metrics": rows, # 真正的测速数据
    }
    metrics_path.write_text( # 把内存里的字典对象 metrics_payload，写成硬盘上的 metrics.json 文件
        json.dumps(metrics_payload, indent = 2, sort_keys = True) + "\n", encoding = "utf-8" # dumps 把 Python 字典 → 变成 JSON 格式字符串（文本），缩进 2 空格，按键名排序，最后加上换行符
    )
    (result_directory / "manifest.json").write_text(
        json.dumps(manifest, indent = 2, sort_keys = True) + "\n",
        encoding = "utf-8",
    )
    shutil.copy2(settings.config_path, result_directory / "config.toml")
    shutil.copy2(settings.dataset_path, result_directory / "dataset.toml")
    _write_csv(result_directory / "summary.csv", rows)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None: 
    """Write a compact table; the JSON artifact retains per-sample timing."""
    fieldnames = [ # CSV 表头
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
    with path.open("w", newline = "", encoding = "utf-8") as csv_file: # 写入模式打开文件
        writer = csv.DictWriter(csv_file, fieldnames = fieldnames) # csv.DictWriter 专门接收字典列表，按 fieldnames 表头把字典写成表格。
        writer.writeheader() # 写入表头
        writer.writerows({field: row[field] for field in fieldnames} for row in rows)


def _build_manifest(numpy: Any, settings: BenchmarkSettings, dataset: DatasetSpec, result_directory: Path, started_at: datetime, finished_at: datetime) -> dict[str, object]: # 生成 manifest 的字典对象
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


def _fingerprint_dataset(dataset: DatasetSpec) -> str: # 数据集指纹，计算 sha256 哈希字符串
    """Hash the generation contract, not the generated data inside timed runs."""
    payload = json.dumps(asdict(dataset), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _numpy_build_configuration(numpy: Any) -> str: # 抓取 Numpy 底层编译链接信息，超级重要！同样的 numpy 版本号，如果一个链接 MKL、一个链接 OpenBLAS，跑分差距巨大。
    """Capture the linked BLAS/LAPACK information without polluting benchmark output."""
    stream = io.StringIO()
    with (
        contextlib.redirect_stdout(stream),
        warnings.catch_warnings(),
    ):
        warnings.simplefilter("ignore", UserWarning)
        numpy.show_config()
    return stream.getvalue()


def _git_metadata() -> dict[str, object]: # 调用系统 git 命令，获取代码仓库信息，如果你改了源码忘记提交，跑出来的实验 manifest 会标记 dirty:true ，提醒别人这份结果来自未提交代码。
    """Return best-effort repository provenance without making repository changes."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd = REPOSITORY_ROOT,
            check = True,
            capture_output = True,
            text = True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd = REPOSITORY_ROOT,
                check = True,
                capture_output = True,
                text = True,
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
    """Anchor relative output paths at repository root rather than the caller CWD.""" # 相对输出路径以仓库根目录为基准，而不是调用方的当前工作目录（CWD）
    if experiment.output_directory.is_absolute(): # 如果是绝对路径：直接原样返回
        return experiment.output_directory
    return REPOSITORY_ROOT / experiment.output_directory # 如果是相对路径：把相对路径拼接到 REPOSITORY_ROOT（仓库根目录）下面再返回 


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
    # 使用指定的 seed，创建一个可以重复生成相同随机序列的 NumPy 随机数生成器
    """Create an explicitly named deterministic random generator."""
    return numpy.random.Generator(numpy.random.PCG64(seed))


def _load_toml(path: Path) -> dict[str, object]: # 读取 TOML 配置文件，把内容转换成 Python 字典并返回。
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("rb") as config_file:
        raw = tomllib.load(config_file)  # raw 是一个字典
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a TOML table at the root of {path}")
    return raw


def _mapping(raw: Mapping[str, object], key: str, path: Path) -> Mapping[str, object]:
    value = raw.get(key) # 取出键所对应的值
    if not isinstance(value, dict):
        raise ValueError(f"Expected [{key}] table in {path}")
    return value


def _required_string(section: Mapping[str, object], key: str, section_name: str) -> str:
    value = section.get(key)
    # 提取例如 cpu_benchmark 中的 dataset 对应的值赋给 value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{section_name}.{key} must be a non-empty string")
    return value


def _positive_int(section: Mapping[str, object], key: str, section_name: str) -> int:
    # 判断 section 中的 key 对应的值是否是正整数
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{section_name}.{key} must be a positive integer")
    return value


def _non_negative_int(section: Mapping[str, object], key: str, section_name: str) -> int:
    # 判断 section 中的 key 对应的值是否是非负整数
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{section_name}.{key} must be a non-negative integer")
    return value


def _number(section: Mapping[str, object], key: str, section_name: str) -> float:
    # 读取一个数值，允许整数或浮点数，排除布尔值，最后统一转换成 float 返回
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{section_name}.{key} must be a number")
    return float(value)


def _positive_number(section: Mapping[str, object], key: str, section_name: str) -> float:
    value = _number(section, key, section_name)
    if value <= 0:
        raise ValueError(f"{section_name}.{key} must be greater than zero")
    return value


def _positive_int_tuple(section: Mapping[str, object], key: str, section_name: str) -> tuple[int, ...]:
    # 检查算子列表的合法性并返回元组
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
    # 返回线性插值分位数，无需添加另一个依赖项
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower) # 线性插值


def _round(value: float) -> float:
    return round(value, 6) # 舍入到小数点后 6 位
