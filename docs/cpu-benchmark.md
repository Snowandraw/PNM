# CPU 算子基准（v1）

本套件是后续 DPU / NPU 卸载实验的 CPU 对照组。它不会下载一个不适合所有算子的
“真实大数据集”，而是依据版本化的 TOML 规范、固定 seed 和 PCG64 在内存中生成输入。
这样同一份输入契约可以被未来的 CPU、DPU 与 NPU backend 复用，且随机数生成和校验不会
进入算子计时。

首个数据规范位于 data/sample/cpu_operator_suite.toml：

| 输入族 | 数据形式 | 算子 |
| --- | --- | --- |
| dense_f32 | 连续 float32 向量 | copy、add、multiply、relu、sum、随机 gather |
| tensor_layout | 连续方阵 float32 | materialized transpose、GEMM |
| records-v1 | 16-byte 记录：flow_id、timestamp、length、flags、value | threshold count、compact filter、histogram |
| payload_u8 | 高熵 uint8 字节流 | CRC32 |

向量规模覆盖约 8 KiB、256 KiB、4 MiB、32 MiB 的单数组工作集。缓存命中会受
CPU 亲和性、预取、其他进程和算子读写数量影响，因此只能把这些规模称为“近似缓存层级”，
不能把小规模的有效带宽称作 DDR 带宽。

## 安装与运行

从 WSL 的 Linux 文件系统运行，不要从 /mnt/c 或 Windows UNC 路径运行：

~~~bash
cd /home/snow/PNM
python -m venv .venv
. .venv/bin/activate
python -m pip install --index-url https://pypi.org/simple -e ".[cpu,dev]"
~~~

当前这台 WSL 的默认 pip 索引没有列出 NumPy，因此示例显式使用官方 PyPI。若组织网络
策略不允许访问它，请改用获准镜像或管理员提供的 wheel，不要绕过组织网络策略。

首轮建议锁定一个逻辑 CPU，确保 NumPy 在导入前已获得线程环境变量：

~~~bash
taskset -c 0 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 pnm-cpu-benchmark --config configs/cpu_baseline.toml
~~~

GEMM 的第二轮可使用八个物理核（7840H 的 WSL 可见 SMT 配对为 0/1、2/3 …）：

~~~bash
taskset -c 0,2,4,6,8,10,12,14 env OPENBLAS_NUM_THREADS=8 OMP_NUM_THREADS=8 \
  MKL_NUM_THREADS=8 pnm-cpu-benchmark --config configs/cpu_baseline.toml
~~~

NumPy 的逐元素 ufunc 通常不会因这些环境变量线性扩展；它们主要影响 BLAS 支撑的
matmul。请分别保存单核和八物理核的目录，不要混合结果。

## 结果结构

每次运行都会创建一个不可覆盖的目录：

~~~text
outputs/cpu-baseline-7840h-wsl/<UTC timestamp>-<config hash>/
  config.toml
  dataset.toml
  manifest.json
  metrics.json
  summary.csv
~~~

metrics.json 保存每个样本的 wall-time / process CPU-time，以及 median、p50、p95、
mean、变异系数、元素吞吐、声明的逻辑有效 GB/s 和估算 GFLOP/s。summary.csv 是适合快速
比较的扁平表。manifest.json 记录 Git commit 与 dirty 状态、Python/NumPy/BLAS 信息、
CPU 亲和性、可见内存、线程环境变量、配置哈希和数据规范指纹。

“有效 GB/s”是算子声明的读写字节数除以 median wall-time；它可能包含缓存效果，也没有
硬件计数器验证，因此不能表述为真实的 DRAM 物理带宽。

## 本机与 WSL 注意事项

- 当前 WSL2 实际可见内存约为 7.4 GiB，而不是宿主机的 16 GiB；v1 的单个 case 已控制在
  远低于这个上限的范围内。
- 先接电、使用高性能模式、关闭重负载应用。7840H 的温度和功耗限制会改变长时间测试结果。
- 当前 WSL 环境没有可用的匹配 perf 工具，因此 v1 只要求 time.perf_counter_ns()。
  cycles、instructions、cache miss、频率与温度留给后续的裸 Linux / 可用 perf 采集器。
- RTX 4060 不参与本套纯 CPU 基准；SSD I/O 也应另建 suite，避免文件系统缓存污染这里的
  内存算子数据。
- 后续比较 DPU 时应分开报告 Host→DPU、DPU kernel、DPU→Host 和端到端时间。copy、
  filter、histogram 与 CRC32 比 GEMM 更接近值得评估 DPU 卸载的路径。
