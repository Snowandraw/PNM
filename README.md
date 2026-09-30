# PNM

PNM（Processing Near Memory）研究工程的可复现实验骨架。仓库用于管理工作负载、
CPU 基线、近存计算模型、实验配置和可追溯的结果说明。当前阶段不依赖 DPU，先建立
稳定的 CPU、内存和存储 I/O 基线，再逐步接入模拟或真实卸载后端。

## 环境要求

项目要求 Python 3.11 或更高版本。服务器参考环境为 Ubuntu 24.04、Python 3.12，
并将虚拟环境放在仓库之外，避免在 Windows 和 Linux 之间复制平台相关文件。

首次配置服务器时安装系统依赖：

```bash
sudo apt update
sudo apt install -y \
  python3.12-venv python3-pip python3-dev \
  build-essential cmake ninja-build \
  fio nvme-cli jq hwloc sysstat libnuma-dev
```

创建并安装项目环境：

```bash
python3 -m venv ~/.venvs/pnm-server
source ~/.venvs/pnm-server/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[cpu,dev]"
```

日常登录后只需执行：

```bash
cd ~/project/PNM
source ~/.venvs/pnm-server/bin/activate
```

## 基础功能验证

```bash
python --version
which python
pnm --config configs/baseline.toml
pytest
ruff check .
```

当前测试应全部通过，`which python` 应指向
`/home/liuhaoqi/.venvs/pnm-server/bin/python`。

## CPU 算子基线

NumPy CPU 算子基线入口为：

```bash
pnm-cpu-benchmark --config configs/cpu_baseline.toml
```

`configs/cpu_baseline.toml` 目前保留原 WSL/7840H 基线参数。正式测量服务器前，
应复制一份服务器专属配置，更新实验名、硬件信息、线程设置和输出目录，避免混淆不同平台的数据。

为了得到可比较的单线程结果，运行前可显式限制数学库线程数：

```bash
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
```

## 目录约定

| 路径 | 用途 | 是否提交到 Git |
| --- | --- | --- |
| `src/pnm/` | 可复用的 PNM 研究代码 | 是 |
| `configs/` | 可复现实验的基线和派生配置 | 是 |
| `scripts/` | 面向研究人员的命令包装脚本 | 是 |
| `tests/` | 配置和核心逻辑的自动化测试 | 是 |
| `data/sample/` | 最小可运行样例数据 | 是 |
| `data/raw/`、`data/interim/`、`data/processed/` | 本地或外部数据集 | 否 |
| `checkpoints/` | 训练或仿真的可再生成状态 | 否（仅说明文件） |
| `outputs/` | 运行日志、指标和图表等结果产物 | 否（仅说明文件） |
| `experiments/` | 每次实验的结论、配置引用及代码版本记录 | 是 |
| `docs/` | 架构决策、术语和实验协议 | 是 |

## 实验工作流

1. 从 `configs/baseline.toml` 复制一份配置并为实验命名。
2. 通过 `pnm --config <配置路径>` 或 `scripts/run_experiment.py` 运行。
3. 将生成的产物保存在 `outputs/<实验名>/`，不要提交大型输出。
4. 在 `experiments/` 新建说明，记录配置路径、Git commit、数据版本、CPU 绑定方式、
   线程环境变量、关键指标和结论。
5. 对正式结果至少进行预热和多次重复测量，并保留原始结果，避免只记录汇总数字。

`pnm` 负责验证并打印实验配置，作为 benchmark、simulator 或训练流程的稳定入口。
GitHub Actions 会在 Python 3.11 和 3.12 上执行静态检查与测试。

## 当前状态

仓库已完成工程骨架和 NumPy CPU 算子基线。下一步是在服务器上建立 P-core、E-core、
全核、内存带宽和 NVMe I/O 的可复现基线，然后定义统一的 CPU 与近存卸载后端接口。
