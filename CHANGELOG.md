# 变更记录

本文件记录项目版本的主要变化、原因和验证情况；Git commit 用于追溯具体代码。
每次功能更新时同步维护本文件与 `pyproject.toml` 的版本号。
实验数据、配置引用和分析结论放在 `experiments/`，设计取舍放在 `docs/`。


## 0.2.0

本次版本说明整理于 2026-10-06，服务器适配及初步验证完成于 2026-10-01。
项目版本已更新为 0.2.0；

### 修改原因

原 CPU 基线配置描述 Ryzen 7 7840H / WSL，不能准确标识 Intel Core Ultra 9 285K
服务器的运行条件。混合架构 CPU 的核心类型与数学库线程数也需要明确控制和记录。

### 新增

- P-core 单核配置 `configs/cpu_server_285k_pcore.toml`：绑定 CPU 2，数学库线程数为 1。
- E-core 单核配置 `configs/cpu_server_285k_ecore.toml`：绑定 CPU 8，数学库线程数为 1。
- 可选的 `[execution]` 配置及对应 `BenchmarkSettings` 字段：运行标签、CPU 亲和性、
  数学库线程数。
- `_configure_execution()`：在 NumPy 导入前应用线程环境变量和 CPU 亲和性；
  请求的 CPU 不在当前允许集合中时报告错误。
- 非空、非负且无重复的 CPU 编号数组校验。
- manifest 中的执行配置、主机名、CPU 型号、电源策略及系统平均负载记录。
- 服务器 P-core 配置解析测试，以及结果环境字段检查。

### 调整

- README 与配置说明补充 Linux 服务器环境和基线运行方式。
- 数据集的缓存规模注释改为通用描述，向量、矩阵、记录和 payload 的规模保持不变。
- manifest 的测量限制说明改为适用于不同平台的用户态 CPU 基线描述。
- 保留原 `configs/cpu_baseline.toml`，用于 WSL/7840H 历史结果追溯。

### 验证记录

2026-10-01 的验证结果：

- 全仓库 pytest：6 项通过。
- P-core 与 E-core 各运行 42 个 case，12 类算子的正确性状态全部通过。
- 两组 manifest 的实际 CPU 亲和性分别为 `[2]`、`[8]`；
  OpenBLAS、OpenMP、MKL、BLIS、NumExpr 线程环境变量均为 `1`。
- `git diff --check` 通过；Ruff 忽略 E501 后通过。
- 完整 Ruff 仍存在上一提交中文注释引起的 58 个 E501 行长问题。

结果目录相对于仓库根目录：

- `outputs/server-285k/cpu-baseline-core-ultra-9-285k-pcore-single/20261001T083335Z-539e09ab/`
- `outputs/server-285k/cpu-baseline-core-ultra-9-285k-ecore-single/20261001T083449Z-64d3d0c3/`

### 当前限制

- 初步结果的 manifest 标记代码为 dirty，不能仅凭基础 commit 重建当时全部改动。
- 测试时 governor 为 `powersave`，EPP 为 `balance_performance`；少数 case 波动较高。
- 内存速率尚未核实；容量描述也需要结合实际安装信息确认。
- 数学库线程变量不等于实际活动线程数监测，也不会自动使所有 NumPy 算子并行。
- 当前测试使用内存生成的数据，尚未包含 NVMe 读取或 DPU 卸载路径。

## 0.1.0 — 初始阶段

- 建立 Python 工程骨架、TOML 配置解析、命令入口、测试和 CI。
- 实现 NumPy CPU 基线：12 类算子、正确性检查、预热和重复采样。
- 输出指标 JSON、汇总 CSV、环境 manifest 及配置和数据集快照。
- 完成原 WSL/7840H 基线配置；CPU 基线初版见提交 `68107f7`（2026-08-26）。
