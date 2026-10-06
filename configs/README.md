# 实验配置

每个可复现实验都应由一个版本控制的 TOML 配置描述。建议从 `baseline.toml` 复制并保留其继承关系或差异说明。

配置中至少应包含：实验名和随机种子、工作负载、硬件/模拟器参数，以及输出目录。不要在配置中保存凭据或本地绝对路径。

CPU 基线配置分为：

- `cpu_baseline.toml`：历史 WSL/7840H 配置，保留用于结果追溯。
- `cpu_server_285k_pcore.toml`：服务器 P-core 单核基线，固定 CPU 2 和单线程数学库。
- `cpu_server_285k_ecore.toml`：服务器 E-core 单核基线，固定 CPU 8 和单线程数学库。

服务器配置中的 `[execution]` 会在 NumPy 导入前应用 CPU 亲和性和线程数，避免依赖调用者手工设置 `taskset` 或环境变量。新增多核配置时应使用新的实验名，并明确记录 CPU 列表和线程数。
