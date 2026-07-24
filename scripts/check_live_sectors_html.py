#!/usr/bin/env python3
import urllib.request
url = "https://alphapilot.api-tokenmaster.com/cn/sectors/"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
checks = {
    "通达信": "通达信" in html,
    "5日": "5日" in html,
    "行业涨跌热力": "行业涨跌热力" in html,
    "行业流入合计": "行业流入合计" in html,
    "今日流入": "今日流入" in html or "流入" in html,
}
print("len", len(html))
for k, v in checks.items():
    print(k, v)
# find script chunks mentioning sector
for token in ["sectors", "HeatStrip", "period_label", "FlowBarChart"]:
    print(token, html.find(token))
