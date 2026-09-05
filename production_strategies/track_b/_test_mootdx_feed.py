# -*- coding: utf-8 -*-
"""
Test mootdx_feed logic offline with mocked mootdx Quotes.
Run:  python production_strategies/track_b/_test_mootdx_feed.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mootdx_mock  # noqa: E402
import mootdx_feed  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS %s %s" % (name, detail))
    else:
        FAIL += 1
        print("FAIL %s %s" % (name, detail))


# 1. _market_code
check("mkt sh suffix", mootdx_feed._market_code("600519.SH") == ("600519", "sh"))
check("mkt sh prefix", mootdx_feed._market_code("600519") == ("600519", "sh"))
check("mkt sz suffix", mootdx_feed._market_code("000001.SZ") == ("000001", "sz"))
check("mkt sz prefix", mootdx_feed._market_code("300750") == ("300750", "sz"))
check("mkt invalid", mootdx_feed._market_code("abc") is None)

# 2. _compute_abr on known data
if mootdx_mock.pd is not None:
    import pandas as pd

    # 30 active buy vol=1 each, 10 active sell vol=1 each, 2 neutral, 8 auction
    rows = []
    for _ in range(30):
        rows.append(["10:00", 11.0, 1, 1, 0, 1])
    for _ in range(10):
        rows.append(["10:00", 11.0, 1, 1, 1, 1])
    for _ in range(2):
        rows.append(["10:00", 11.0, 1, 1, 2, 1])
    for _ in range(5):
        rows.append(["09:25", 11.0, 1, 1, 8, 1])
    df = pd.DataFrame(rows, columns=["time", "price", "vol", "num",
                                     "buyorsell", "volume"])
    abr, buy, sell, n = mootdx_feed._compute_abr(df)
    check("abr known", abr == 0.75, "abr=%s" % abr)
    check("buy vol", buy == 30, "buy=%s" % buy)
    check("sell vol", sell == 10, "sell=%s" % sell)
    check("n total rows incl 2/8", n == 47, "n=%s" % n)

    # empty
    abr2, _, _, _ = mootdx_feed._compute_abr(None)
    check("abr None on empty", abr2 is None)

    # all auction/neutral
    rows2 = [["09:25", 11.0, 1, 1, 8, 1], ["09:25", 11.0, 1, 1, 2, 1]]
    df2 = pd.DataFrame(rows2, columns=["time", "price", "vol", "num",
                                       "buyorsell", "volume"])
    abr3, _, _, _ = mootdx_feed._compute_abr(df2)
    check("abr None when no 0/1", abr3 is None)
else:
    print("pandas missing, skip compute tests")


# 3. Feed refresh+save with mocked client
real_quotes = mootdx_feed.Quotes
mootdx_feed.Quotes = mootdx_mock._MockQuotes  # monkeypatch
try:
    tmp = tempfile.mkdtemp(prefix="mootdx_test_")
    feed = mootdx_feed.MootdxFeed(out_dir=tmp, symbols=["600519.SH", "000001.SZ"])
    updates = feed.refresh()
    check("refresh returns 2", len(updates) == 2, "got=%d" % len(updates))
    if updates:
        sym, rec = sorted(updates.items())[0]
        check("abr in [0,1]", 0.0 <= rec["abr"] <= 1.0, "sym=%s abr=%s" % (sym, rec["abr"]))
        check("buy+sell>0", (rec["buy_vol"] + rec["sell_vol"]) > 0, str(rec))
        check("n>0", rec["n"] > 0)
    path = feed.save()
    import json
    data = json.load(open(path, "r", encoding="utf-8"))
    check("saved json has 2 syms", len(data) == 2, "got=%d" % len(data))
    check("saved json has abr", all("abr" in v for v in data.values()))
finally:
    mootdx_feed.Quotes = real_quotes  # restore


print("")
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
