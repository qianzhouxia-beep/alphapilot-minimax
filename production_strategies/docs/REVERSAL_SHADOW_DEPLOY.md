# 尾盘超跌×低开影子方案 — 部署说明

> 路径 C 影子先行阶段。2026-08-29 设计，本地冒烟测试通过，**2026-08-29 10:45 已部署服务器**（srv_ssh 自动通道，无人工参与）。
> 关联：`docs/超跌反包因子融合方案_2026-08-29.md`（路径 C）、`knowledge/inbox/2026-08-29-weak-reversal-lowopen-increment.md`。

## 一句话

在服务器 14:50 每天扫描全市场「弱市超跌×低开」组合，只记录候选不下单；T+1 收盘后结算并推企业微信。**不改 P2 任何链路。**

## 信号口径（与回测一致）

- 连跌≥3 天（`down_streak>=3`，14:50 当日基本定型）
- 长上影：当日 `upper_shadow > 历史 60% 分位`（滚动历史分位，无前视）
- 120 日低位：`pos120 < 历史 40% 分位`
- 近 5 日无跌停（`has_lu_down5=False`）
- 大盘 3 日累计跌（`mkt3<=0`，等权全市场代理）
- 低开（当日 `open_gap<0`）
- 候选按 `open_gap` 升序（低开越深越优先），取 Top20

## 文件

| 文件 | 作用 | 部署位置 |
|---|---|---|
| `scripts/reversal_shadow_scanner.py` | 14:50 全市场扫描 → `output/reversal_shadow/{date}.json` + 追加 history.jsonl | 服务器根目录 |
| `scripts/reversal_shadow_report.py` | T+1 结算 → `output/reversal_shadow_report.{md,json}` → 企业微信推送 | 服务器根目录 |

## Cron（服务器）

```bash
# 14:50 尾盘扫描（工作日）
50 14 * * 1-5 cd /home/ubuntu/alphapilot && python3 -u scripts/reversal_shadow_scanner.py >> output/logs/reversal_shadow.log 2>&1
# 16:30 结算+推送（K线 16:18 已同步）
30 16 * * 1-5 cd /home/ubuntu/alphapilot && python3 -u scripts/reversal_shadow_report.py >> output/logs/reversal_shadow.log 2>&1
```

⚠️ 按 `production_strategies/server/README.md` 规范改 crontab：先 SFTP 写 `/tmp/crontab_new.txt`，再 `crontab < /tmp/crontab_new.txt`，改完 `crontab -l` 双重验证 + 备份 `/tmp/cron_bak_YYYYMMDD.txt`。**禁止** `echo | base64 | crontab -` 管道。

## 数据依赖

- `data/kline_cache/kline_all.parquet`：因子计算（pos120 需 120 日窗口，scanner 自己拉 mootdx 实时，report 用当日收盘缓存）
- 大盘开关：scanner 用等权全市场 `mkt3`（自算）；report 无依赖
- 企业微信：`config/wecom_webhook.conf`（已部署，0600），`wecom_push.py` 自动读取

## 环境变量

- `ALPHAPILOT_ROOT`：默认 `/home/ubuntu/alphapilot`；本地开发时设本地路径
- `REVERSAL_SHADOW_DISABLE=1`：关闭扫描
- `--no-skip`：大盘开关不满足也记录（用于积累全样本）

## 本地测试（已验证）

```bash
# scanner 冒烟（用历史 parquet 做 pool-file）
python scripts/reversal_shadow_scanner.py --date 2026-08-21 --pool-file data/kline_cache/kline_all.parquet
# report 结算（无推送）
python scripts/reversal_shadow_report.py --no-send
```

本地无 wecom 配置时推送返回 `no_webhook`，不报错。生产已有配置。

## 验证清单（上线前）

- [x] 服务器部署两个脚本 + cron 两行（2026-08-29 10:45，crontab 136→138 行，双重验证通过）
- [x] 服务器冒烟：`--date 2026-08-28 --pool-file kline_all.parquet` 正常出分位/大盘开关/落盘（弱市 OFF 无候选为预期）
- [ ] 连续 2 周影子记录（只写不对单）
- [ ] 影子候选 / 日 ≥1 只（弱市 arm 时）
- [ ] 报告推送企业微信成功（ok=True）
- [ ] 影子累计 n≥30 后与回测基准 62.4% 对比，样本外确认
