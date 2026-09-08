# AlphaPilot + QMT (XtQuant) 实盘集成指南

## 概述

AlphaPilot 现在的 `trade_executor.py` 支持两种运行模式：

| 模式 | ENABLE_QMT | 执行方式 |
|---|---|---|
| Paper（纸盘） | 0（默认） | 读写 `paper_trading.json`，模拟成交，前端可视化 |
| QMT（实盘） | 1 | 通过 XtQuant API 向 MiniQMT 发送真实委托，同时镜像写入 `paper_trading.json` 做数据记录 |

## 架构

```
paper_trading_signals.py (选股信号)
         |
         v
trade_executor.py (成交执行器)
     |         |
     |    paper_trading.json  ← 始终写入（数据记录+前端展示）
     |         |
     v         v
qmt_bridge.py → MiniQMT → 券商柜台 → 交易所
(ENABLE_QMT=1 时)
```

- **安全默认**: `ENABLE_QMT=0`，不会向券商发送任何真实订单
- **双向记录**: QMT 模式下，真实成交的同时也写入 `paper_trading.json`，前端 Dashboard 数据一致
- **导入安全**: 即使未安装 xtquant，导入不会崩溃，自动降级为 paper 模式

## 前置条件

### 1. 开通 QMT 量化交易
- 联系券商（华泰/国金等）开通 QMT 量化交易权限
- 下载 MiniQMT 客户端并安装

### 2. 安装 xtquant Python 包

```bash
# 方式 A: pip 安装（推荐）
pip install xtquant

# 方式 B: 从迅投官网下载对应 Python 版本的 .whl
# https://dict.thinktrader.net/nativeApi/start_now.html
```

### 3. 启动 MiniQMT 客户端

Windows 桌面：
1. 打开 MiniQMT 客户端
2. 登录资金账号
3. 保持 MiniQMT 运行状态（托盘图标常驻）

## 配置

### 编辑 `config/qmt.env`

```bash
# MiniQMT 客户端 userdata_mini 路径
# Windows 上通常在这里:
MINI_QMT_PATH=C:\Program Files\thinktrader\MiniQMT\userdata_mini

# 资金账号 (留空=自动获取第一个股票账户)
ACCOUNT_ID=

# 会话ID (默认 123456)
SESSION_ID=123456

# 启用实盘模式
ENABLE_QMT=1
```

### 打开实盘模式

```bash
# 方式 A: 在 config/qmt.env 中设置
echo "ENABLE_QMT=1" > config/qmt.env

# 方式 B: 环境变量覆盖
export ENABLE_QMT=1
```

## 运行

```bash
cd /home/ubuntu/alphapilot

# Paper 模式（默认，无需任何改动）
python3 trade_executor.py

# QMT 实盘模式
ENABLE_QMT=1 python3 trade_executor.py
```

## 首次验证

```bash
# 1. 测试 qmt_bridge 能否导入
python3 -c "from qmt_bridge import QmtBridge; print('OK')"

# 2. 检查连接状态
python3 -c "from qmt_bridge import get_bridge; b=get_bridge(); print(b.status)"

# 3. 配置正确后，启动 MiniQMT 客户端，再测试连接
ENABLE_QMT=1 python3 qmt_bridge.py
```

## 模块说明

### `qmt_bridge.py`
QMT 桥接核心模块，提供：
- `fetch_quote_tuple(symbol)` — 返回 `(last, prev_close, open, high)`，兼容原 `fetch_quote()`
- `buy(symbol, price, quantity, strategy)` — 限价/市价买入
- `sell(symbol, price, quantity, strategy)` — 限价卖出
- `get_account()` — 查询账户资产
- `get_positions()` — 查询持仓
- `get_kline(symbol)` — 获取历史K线

### `trade_executor.py`
统一成交执行器，自动检测 QMT 可用性：
- `_QMT_READY=True` → 买卖操作同时发往 QMT + 写入 paper_trading.json
- `_QMT_READY=False` → 只写入 paper_trading.json（原模拟盘行为）

## 风险提示

1. **先用小资金测试**: 首次启用 QMT 实盘时，建议用 1-2 万元资金验证链路的正确性
2. **保留 paper 模式**: `ENABLE_QMT=0` 时完全不影响现有模拟盘逻辑
3. **MiniQMT 需手动启动**: QMT 客户端必须保持运行，交易才会执行
4. **幂等安全**: 同一策略的同一信号只会处理一次（`traded_symbols` 去重）
5. **T+1 合规**: 当前版本的止盈止损逻辑仍使用简易版（成本 +8%/-6%），后续可升级为完整的 4 层动态出场

## 回滚

```bash
# 恢复为纯 paper 模式版本
cp trade_executor.py.bak trade_executor.py

# 或关闭 QMT
echo "ENABLE_QMT=0" > config/qmt.env
```
