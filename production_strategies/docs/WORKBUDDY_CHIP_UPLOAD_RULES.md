# WorkBuddy 筹码上传铁律（2026-08-25 起强制）

> 本文件是给 **WorkBuddy** 的操作约束。你（WorkBuddy）负责从本地拉取东财真实 CYQ 筹码并上传到上海服务器。
> **每次上传必须遵守本规则，否则会重演 08-24 事故。**

---

## 一、为什么必须有这条规则（08-24 事故）

- 08-24 你生成的批次文件 `_chip_batch_{NN}_0824.json` 只有 **19 个批次（00~17 + 20）**，
  **缺失 18、19 两个批次（400 只）**，加上其他零头共 1192 只没拉到。
- 你照常跑了 `_upload_chip_0824.py` 上传 → 服务器对这 1192 只保留旧数据（停在 08-21）。
- 结果：`chip_data_all.json` 中 1192 只筹码日期停在 08-21，其余 3800 只已是 08-24，
  **半截数据进入生产选股链路，且多道检查没拦住**（服务器闸门此前只查"众数日"）。

**教训：批次不完整 = 不许上传。** 宁可当天不上传，也不能传半截数据。

---

## 二、上传前必跑校验（硬性步骤）

在你生成完当天全部 `_chip_batch_{NN}_{YYYYMMDD}.json` 之后、运行 `_upload_chip_*.py` **之前**，必须执行：

```bash
python scripts/check_chip_batches.py --date $(date +%F)
```

（在批次文件所在目录执行；服务器上该脚本位于 `/home/ubuntu/alphapilot/scripts/check_chip_batches.py`，
本地副本在 `production_strategies/server/check_chip_batches.py`）

**校验三项，全部通过才算 OK（退出码 0）：**

| 检查项 | 通过标准 | 失败后果 |
|---|---|---|
| 批次连续性 | 批次号 00~N 连续，无缺失 | 缺 1 批 ≈ 漏 200 只 → 禁止上传 |
| 总覆盖率 | 合并后 ≥ 4850 只 | 覆盖率不足 → 禁止上传 |
| 日期匹配 | 最新日期 == 目标日期 | 数据不是当日 → 禁止上传 |

**校验不通过时：**
1. 找出缺失的批次号（脚本会打印，如 `缺失: [18, 19]`）。
2. **补拉缺失批次的筹码数据**，重新生成对应 `_chip_batch_*.json`。
3. 重新跑校验，直到 `结果: 通过，可上传`。
4. **严禁**在校验不通过的情况下运行上传脚本。

---

## 三、上传脚本模板更新（建议，从下一个交易日开始）

你每天生成的 `_upload_chip_{YYYYMMDD}.py` 请在开头加入校验（在合并本地批次之前）：

```python
import subprocess, sys
# ── 上传前批次完整性校验（2026-08-25 强制）──
r = subprocess.run(
    [sys.executable, "scripts/check_chip_batches.py", "--date", "YYYYMMDD"],
    capture_output=True, text=True,
)
print(r.stdout)
if r.returncode != 0:
    print("[UPLOAD BLOCKED] 批次校验不通过，禁止上传。请先补拉缺失批次。")
    sys.exit(1)
```

> 注意：`--date` 传 `YYYYMMDD`（如 `20260825`）或 `YYYY-MM-DD` 均可，脚本自动识别。

---

## 四、服务器侧已有防线（不需要你操作，但要知晓）

- `16:15` fix_kline 串行拉 K 线，**最新日覆盖率 <90% 拒绝写入**。
- `18:15` daily_coverage_check 全数据复查（含 chip 覆盖率 <95% 告警）——**在你上传之后跑**。
- `04:50` data_readiness_gate：chip 最新日覆盖率 **≥95% 才 ready**，否则早晨选股会被标记。
- **FAIL 才推企业微信**（2026-08-25 起）：`ready=True` 静默；仅 critical fail 时 WeCom 一条告警（同日同原因去重）。你 PASS 不必日报，两边对齐。

所以你上传越早（建议 17:30 前），18:15 的复查越能兜住你的遗漏。

---

## 五、常见问题

- **为什么不能直接用 `pull_chip_from_kline.py` 兜底？**
  那是 K 线推演口径，与东财真实 CYQ 筹码不同，会污染生产筹码数据。生产 chip **只认你上传的真实数据**。
  如果当天实在补不齐，宁可不传（服务器会用前一天的全量数据，闸门会告警但不阻断次日选股）。

- **上传前怎么确认覆盖全？**
  批次号连续 + `check_chip_batches.py` 报 `覆盖 ≥ 4850` 即可。全市场约 4991 只，留 ~3% 新股/停牌余量。

- **如果本地批次文件名格式变化？**
  保持 `_chip_batch_{两位序号}_{MMDD}.json` 或 `_chip_batch_{两位序号}_{YYYYMMDD}.json` 均可，
  校验脚本两者都认。不要改序号编码格式。
