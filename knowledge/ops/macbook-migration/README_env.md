# AlphaPilot 迁移环境文件（2026-09-05 生成）

给 MacBook 装环境用。三台机器的 Python 差异很大，**不要跨版本硬灌**：

| 机器 | 系统 | Python | 说明 |
|---|---|---|---|
| 这台 PC（迁移源） | Windows | 3.14.5 (`C:\Python314`) | 当前开发/回测主力，无 venv，全局包 326 个 |
| MacBook（迁移目标） | macOS | **建议 3.14**（brew/uv 装） | 从 `requirements_pc_py314_full.txt` 重建即可与原 PC 一致 |
| 上海生产机 | Ubuntu | 3.10.12（`/usr/bin/python3`，pip 用户级 `~/.local`） | **只读参照**：生产运行时不从这里 pip 装，别用 py3.10 的 pins 上 Mac |

## 用法

### MacBook（替代这台 PC）
1. 装 Python 3.14：`brew install python@3.14` 或 `uv python install 3.14`
2. `python3.14 -m venv .venv && .venv/bin/pip install -r requirements_pc_py314_full.txt`
   - 若个别包在 macOS 上无对应 wheel（概率低，PC pins 都是较新版本、普遍有 mac arm64 轮子），单独降级该包即可；核心依赖兜底用下面 runtime-core 那份。
3. 运行入口照旧：`alphapilot_pipeline_v3.py`（选股）/ `run_server.py`、`api_server.py`（服务）/ 回测 `bt_research/`

### 对照参考
- `requirements_shanghai_py310_full.txt`：上海机 `pip freeze` 原样（313 包），仅用于比对生产依赖，勿直接 install 到 Mac。

## runtime-core 兜底清单（若 freeze 全量装不动）
pandas numpy scipy scikit-learn lightgbm xgboost requests akshare
pyarrow fastparquet paramiko tqdm matplotlib openpyxl fastapi uvicorn pydantic

---
生成方式（复现）：
- PC：`python -m pip freeze`
- 上海机：`ssh ubuntu@150.158.100.236 "python3 -m pip freeze"`
