---
project: alphapilot
domain: architecture
title: Shadow 自动报告已接企业微信群机器人推送（Webhook + Excel 文件落地）
date: 2026-08-16
updated: 2026-08-17
status: conclusion
tags: [shadow, 微信推送, wecom, webhook, 自动报告, cron, excel]
---

# Shadow 自动报告 → 企业微信推送（已落地）

## 结论

`scripts/shadow_top2_report.py`（cron 16:26 工作日）生成对比报告后，自动：
1. 调用 `scripts/wecom_push.py` 推送 markdown 摘要（纯文本行，不用表格——企业微信 markdown 不支持表格/代码块）；
2. **生成 Excel 报告并作为文件附件推送**（同早盘选股 `send_daily_picks_excel.py` 的体验）。

**链路已端到端验证：08-17 首次真实运行，markdown 摘要 + Excel 文件均推送成功（ok=True）。**

## 落地细节

- **Webhook 配置**：服务器 `config/wecom_webhook.conf`（0600，只记录不发代码）。URL 格式 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...`。
- **读取逻辑（修正后）**：`wecom_push._webhook()` 优先 env `WECOM_WEBHOOK` → `WECOM_WEBHOOK_FILE` → **自动回退 `config/wecom_webhook.conf`**（cron 无需设 env，已验证无变量环境下自动检测成功）。
- **推送内容（08-17 升级）**：
  - markdown 摘要：日期 + 结论（NO_DATA / NO_CONCLUSION 累积中 / CAND_BETTER / PROD_BETTER / INCONCLUSIVE）+ 生产/候选 T+1/T+2 汇总 + 今日对局明细（选股/名称/T0收盘/T+1/T+2）+ 最近 5 天逐日对比。
  - **Excel 附件**：`output/excel_shadow/AlphaPilot影子对比_YYYY-MM-DD.xlsx`，含 4 个 Sheet：汇总 / 逐日对比（候选更优行绿色高亮）/ 明细 / 说明。依赖 openpyxl（服务器 3.1.5 已确认）。
- **08-17 首次真实记录**：生产 Top1 = 候选 Top1 = 湖南白银(002716)，T0收盘 9.49；生产 Top2 只出 1 只（资金门后仅 1 只 money_flow_pass，宁缺毋滥）；实盘信号 0 买入（盘中资金重排无候选，未下单）。
- **验证记录**：08-16 链路测试 ×4（text/markdown/E2E mock/cron 回退）全成功；08-17 真实推送 markdown + Excel 全成功。

## 来源

用户 2026-08-15 要求"自动调用脚本出结果 + 推送到微信"；08-17 反馈手机端看不到报告内容 → 改纯文本行渲染；再反馈"报告能不能单独文档发一下，就和早上的 Excel 一样" → 加 Excel 文件推送。

## 待办

- [ ] 08-19 起报告开始出现带 T+1/T+2 实值的样本；累计 ≥8 天自动下结论。
- [ ] 若 webhook 泄漏或需停推：删 `config/wecom_webhook.conf` 即可（wecom_push 优雅降级 no_webhook）。
