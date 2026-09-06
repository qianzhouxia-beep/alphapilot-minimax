# 同花顺官方数据只读旁路（补缺口、先观察）

> project: alphapilot | domain: data | status: decision
> date: 2026-08-22 | tags: 同花顺, hithink, 涨停池, 集合竞价, 只读旁路

## 结论

用户纠正：补缺口必须能作用在 **P2 / 09:35 实时选股旁支**，不是 15:40 落盘了事。15:40 归档对当天选股**零影响**。

## 两层落地

1. **15:40 归档**（`hithink_overlay.py`）：涨停/炸板/热股/龙虎榜，供复盘，不改选股。
2. **09:35 P2 旁支**（`hithink_p2_side.py`，接进 `morning_live_fund_select.py`）：
   - **不大管线**：不改 05:00 VM2.5 打分
   - 已涨停 / 热股前5且涨幅>7% → 降权（防追高，对齐 P2「不选已启动票」）
   - 今日涨停扎堆的板块 → 池内同主题但未涨停的票 +8% 分
   - 竞价低开微加、高开>5% 微减
   - 开关 `HITHINK_P2_SIDE` **默认关**（只标注，不改 score / 不改 Top2）；失败不阻断 09:35

## 体现位置

`output/morning_live_picks.json` 每条可带 `hithink_hot_rank` / `hithink_limit_up` / `hithink_side_note` / `hithink_side_mult`。默认只标注，不改 Top2。


## 落地

- 脚本：`scripts/hithink_overlay.py`
- 产出：`output/hithink_overlay.json` + `output/hithink_archive/YYYY-MM-DD.json`
- 服务器 cron：工作日 15:40（收盘后只读落盘）
- Key：`config/hithink_api_key.conf`（0600，不进 git）；本机 `~/.hithink_finance_api_key`

## 明确不改

- `recommend.py` / VM2.5 特征
- 5 点管线选股漏斗
- 09:35 Top2 排序（回测后确认不加）

## 08-21 干跑

涨停 54 / 跌停 13 / 炸板 18 / 热股 30 / 龙虎榜 61 / 竞价快照对观察池 21~30 只。9/9 源成功。

## 回测结论（同日）

as-of 回测否决排序接入。详见 `knowledge/inbox/2026-08-22-hithink-p2-factor-bt.md`。
