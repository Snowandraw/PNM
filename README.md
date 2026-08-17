# PNM
## 2026/8/17
PNM（Processing Near Memory）研究工程的可复现实验骨架。这里存放工作负载、近存计算模型、实验配置及其可追溯的结果说明，具体算法和硬件实现可在此基础上逐步加入。
### 环境搭建 & 基础功能验证
项目使用 Python 3.14.6 版本，配置文件采用标准库支持的 TOML 格式。
```powershell
& "$HOME\.local\bin\python3.14.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pnm --config configs/baseline.toml
pytest
```
### 目录约定
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
### 实验工作流
1. 从 `configs/baseline.toml` 复制一份配置并为实验命名。
2. 通过 `pnm --config <配置路径>` 或 `scripts/run_experiment.py` 运行。
3. 将生成的产物保存在 `outputs/<实验名>/`，不要提交大型输出。
4. 在 `experiments/` 新建说明，记录配置路径、Git commit、数据版本、关键指标和结论。
`pnm` 当前会验证并打印实验配置，作为后续 benchmark、simulator 或训练流程的稳定入口。
### 开发检查
```powershell
ruff check . 
pytest
```
GitHub Actions 会在 Python 3.11 和 3.12 上执行同样的静态检查与测试。
### 当前状态
仓库已完成工程骨架。下一步建议先确定一个基准工作负载和评估指标，再在 `src/pnm/kernels/`、`src/pnm/models/` 中实现对应逻辑。
究仓库