# -*- coding: utf-8 -*-
"""
Test the mootdx integration seam in TrackB_track_b_qmt_auction_sim.py.

We import the QMT strategy module with a fake 'C' ContextInfo (mimicking
C.get_market_data_ex etc.), create a mootdx feed JSON in a temp dir, and
verify _get_active_buy_ratio() prefers fresh mootdx data and falls back to
the L1 tick approximation when the feed is missing/stale.

Run:  python production_strategies/track_b/_test_qmt_mootdx.py
"""
import json
import os
import sys
import tempfile
import time

SRC = r"C:\Users\elvisq\Projects\alphapilot\production_strategies\track_b"
sys.path.insert(0, SRC)

# The QMT strategy file is pure ASCII; import it under a temp filename so its
# module-level config uses the paths we monkeypatch below.
import importlib.util
import types

mod = types.ModuleType("TrackB_track_b_qmt_auction_sim")
src_path = os.path.join(SRC, "TrackB_track_b_qmt_auction_sim.py")
with open(src_path, "r", encoding="utf-8") as f:
    code = f.read()
exec(compile(code, src_path, "exec"), mod.__dict__)
T = mod

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


# ---- fake QMT ContextInfo ----
class FakeC(object):
    def get_market_data_ex(self, fields, codes, period="tick", count=120,
                           subscribe=True, end_time=""):
        # 120 ticks: 60 active buy (price>=ask1), 40 active sell (price<=bid1)
        rows = {"lastPrice": [], "askPrice1": [], "bidPrice1": [],
                "volume": []}
        for i in range(120):
            rows["lastPrice"].append(10.05 if i < 60 else 9.95)
            rows["askPrice1"].append(10.00)
            rows["bidPrice1"].append(10.00)
            rows["volume"].append(100)
        # mimic QMT tick DataFrame: indexable by column name -> list
        class DF(object):
            def __init__(self, data):
                self._d = data

            @property
            def columns(self):
                return list(self._d.keys())

            def __getitem__(self, name):
                return _Series(self._d[name])

            def __len__(self):
                return len(self._d["lastPrice"])

        class _Series(object):
            def __init__(self, vals):
                self._v = vals

            @property
            def values(self):
                return self._v

            def __len__(self):
                return len(self._v)

            def __getitem__(self, i):
                return self._v[i]

        return {codes[0]: DF(rows)}

    def get_instrument_detail(self, code):
        return {"PreClose": 10.0, "UpStopPrice": 11.0, "FloatShares": 1e8}

    def get_stock_list_in_sector(self, sec):
        return []

    def get_industry(self, code):
        return ""


# ---- monkeypatch feed dir to temp ----
tmp = tempfile.mkdtemp(prefix="qmt_mootdx_")
T.MOOTDX_FEED_DIR = tmp
T.USE_MOOTDX_ACTIVE_BUY = True
T.MOOTDX_FEED_MAX_AGE_SEC = 60

fc = FakeC()

# ---- Case 1: fresh mootdx feed preferred ----
today = time.strftime("%Y%m%d")
feed = {today + ".json": {
    "600519.SH": {"abr": 0.42, "buy_vol": 100, "sell_vol": 138,
                  "ts": int(time.time()), "n": 800},
}}
path = os.path.join(tmp, today + ".json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(feed[today + ".json"], f, ensure_ascii=False)
abr = T._get_active_buy_from_mootdx("600519.SH")
check("mootdx fresh read", abr is not None and abr[0] == 0.42,
      "got=%s" % (abr,))
abr_ratio = T._get_active_buy_ratio(fc, "600519.SH")
check("ratio uses mootdx", abr_ratio == 0.42, "got=%s" % abr_ratio)
src, _ = T._get_active_buy_from_mootdx("600519.SH")
check("abr_src mootdx", src is not None)

# ---- Case 2: stale feed -> fallback to L1 ----
stale = {today + ".json": {
    "600519.SH": {"abr": 0.42, "buy_vol": 100, "sell_vol": 138,
                  "ts": int(time.time()) - 3600, "n": 800},
}}
with open(path, "w", encoding="utf-8") as f:
    json.dump(stale[today + ".json"], f, ensure_ascii=False)
abr = T._get_active_buy_from_mootdx("600519.SH")
check("mootdx stale -> None", abr is None or abr[0] is None,
      "got=%s" % (abr,))
abr_ratio = T._get_active_buy_ratio(fc, "600519.SH")
check("ratio falls back to L1", abr_ratio is not None and 0.0 <= abr_ratio <= 1.0,
      "got=%s" % abr_ratio)

# ---- Case 3: missing feed file -> fallback ----
for f in os.listdir(tmp):
    os.remove(os.path.join(tmp, f))
abr = T._get_active_buy_from_mootdx("600519.SH")
check("mootdx missing file -> None", abr is None or abr[0] is None)
abr_ratio = T._get_active_buy_ratio(fc, "600519.SH")
check("ratio fallback on missing file", abr_ratio is not None,
      "got=%s" % abr_ratio)

# ---- Case 4: master switch off -> always L1 ----
T.USE_MOOTDX_ACTIVE_BUY = False
with open(path, "w", encoding="utf-8") as f:
    json.dump(feed[today + ".json"], f, ensure_ascii=False)
abr = T._get_active_buy_from_mootdx("600519.SH")
check("switch off -> mootdx None", abr is None or abr[0] is None,
      "got=%s" % (abr,))
abr_ratio = T._get_active_buy_ratio(fc, "600519.SH")
check("switch off -> L1", abr_ratio is not None)
T.USE_MOOTDX_ACTIVE_BUY = True

print("")
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
