

@app.get("/api/v1/cn/indices/intraday")
async def get_indices_intraday():
    """获取三大指数日内分时数据（东方财富）"""
    import urllib.request, json
    em_codes = {
        "上证指数": "1.000001",
        "深证成指": "0.399001",
        "创业板指": "0.399006",
    }
    result = {}
    for name, secid in em_codes.items():
        url = f"https://push2.eastmoney.com/api/qt/stock/trends2/get?fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&secid={secid}&ndays=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            trends = data.get("data", {}).get("trends", [])
        except Exception:
            trends = []
        points = []
        for t in trends:
            parts = t.split(",")
            if len(parts) >= 2:
                points.append({"time": parts[0], "price": float(parts[1])})
        result[name] = {"points": points, "count": len(points)}
    return result
