# 脚本入口

脚本用于包装稳定的研究命令，不承载核心算法。安装项目后，可优先通过 `pnm` 命令运行；`run_experiment.py` 提供等价的 Python 脚本入口。

## 服务器 CPU 重复测试

在仓库根目录、已激活 `pnm-server` 虚拟环境的 Linux 终端执行：

```bash
python scripts/run_cpu_sweep.py --rounds 3
```

默认顺序包含 P 核 1 线程、E 核 1 线程，以及 P 核 2/4/8 线程，每轮轮换起始配置。所有测试串行运行，每次启动独立 Python 进程，确保数学库线程设置在 NumPy 导入前生效。不会自动修改系统频率、电源策略、缓存状态或其他用户进程。

这五份配置使用同一数据集，预热 5 次、测量 15 次、目标采样时长 50 ms。2 线程使用 CPU 2/5，4 线程使用 CPU 0/1/2/5，8 线程使用 CPU 0–7，按当前 285K 的 P 核编号配置。其他机器必须先核对拓扑，不能直接照搬 CPU 编号。

可选配置子集：

```bash
python scripts/run_cpu_sweep.py --rounds 5 --configs \
  configs/cpu_server_285k_pcore.toml configs/cpu_server_285k_ecore.toml
```

每次 suite 保存到 `outputs/server-285k-sweeps/<时间戳-随机标识>/`，不会覆盖历史结果：

- `suite_manifest.json`：轮次、执行顺序、Git 状态、每次运行的结果路径和前后平均负载。失败或中断会记录状态，并停止后续测试。
- `aggregate.json`：先取每次独立运行的 `median_ms`，再取这些中位数的中位数。同时记录运行间最小/最大值、运行间 CV，以及运行内 CV 的中位数。三轮只能用于初步重复性观察。
- `source_snapshot/`、`source_sha256.json`、`working_tree.patch`：保留实验所用源码和配置，追溯未提交改动。不将 `dirty` 伪装成干净提交。
- `pip-freeze.txt`：当前环境快照。不包含系统库、BIOS 或完整系统镜像，不能单凭它认定两台机器环境完全相同。
- 各轮次目录：原有 `manifest.json`、`metrics.json`、`summary.csv`、配置/数据集快照，以及子进程日志。

这是重复访问相同输入的热缓存测试，不是存储 I/O 或冷缓存测试。`thread_count` 是数学库线程控制，不意味着所有 NumPy 算子都会并行。逻辑 GB/s 也不是物理 DDR 带宽。

## 后续跨机器对比

固定 CPU 基线的 NumPy 版本见 `requirements/cpu-benchmark.txt`。当前服务器 Python 为 3.12.3；本地历史结果的 Python/NumPy、采样参数和 OS 不同，因此只保留为历史参考。正式跨机器对比应使用相同源码、数据集、Python/NumPy/BLAS 版本和采样参数，并重新记录系统库（例如 zlib）、CPU 亲和性、电源策略及后台负载。不要在共享环境中直接升级依赖；应先准备独立环境。
