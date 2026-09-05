# -*- coding: utf-8 -*-
"""
mootdx_feed.py -- Free Level2-like tick feed for AlphaPilot Track B.

Writes active-buy ratios from TDX tick-by-tick transactions into a local
JSON file that the QMT Track B strategy consumes. This bypasses paid QMT
Level2 permission while still giving real active-buy/sell direction per tick.

Data source : mootdx (open-source TDX protocol client, free, no API key)
Frequency  : poll every TICK_POLL_SEC seconds during trading hours
Output     : C:/alphapilot/l2_feed/{YYYYMMDD}.json  (or configured path)
             {"code": {"abr": 0.42, "buy_vol": 1234, "sell_vol": 1500,
                        "ts": 1755331200, "n": 800}, ...}

Consumed by: track_b_qmt_auction_sim.py / _live via _get_active_buy_from_mootdx()

NOTE: only meaningful during trading hours (09:15-15:00 Mon-Fri).
      Outside trading hours tick data is empty; the JSON keeps last snapshot.
"""
import argparse
import json
import os
import time
import warnings

warnings.filterwarnings("ignore")

# ---------------- config ----------------
DEFAULT_OUT_DIR = r"C:\alphapilot\l2_feed"
POLL_SEC = 20                 # poll interval
TRADING_START = (9, 15)       # include call auction phase
TRADING_END = (15, 0)
MAX_SYMBOLS_PER_CALL = 40     # mootdx transaction() is per-symbol; we loop

try:
    from mootdx.quotes import Quotes
except ImportError:
    Quotes = None


def _market_code(symbol):
    """Convert '600519.SH' / '600519' -> ('600519', 'sh'|'sz'|'bj')."""
    s = str(symbol or "").strip()
    if not s:
        return None
    if "." in s:
        code, mkt = s.split(".", 1)
    else:
        code, mkt = s, ""
    code = code.strip()
    if not code.isdigit():
        return None
    mkt = mkt.upper()
    if mkt == "SH" or code.startswith(("6", "9", "5")):
        return code, "sh"
    if mkt == "SZ" or code.startswith(("0", "2", "3", "1")):
        return code, "sz"
    return code, "bj"


def _is_trading_time(now=None):
    now = now or time.localtime()
    if now.tm_wday >= 5:
        return False
    hm = (now.tm_hour, now.tm_min)
    return TRADING_START <= hm <= TRADING_END


def _compute_abr(df):
    """Active-buy ratio from TDX transaction rows.

    buyorsell semantics (mootdx/tdx):
        0 = active buy (外盘), 1 = active sell (内盘),
        2 = neutral, 8 = call-auction match.
    We count only 0/1 into the ratio; 2/8 excluded.
    Returns (abr, buy_vol, sell_vol, n) or (None,0,0,0).
    """
    if df is None or len(df) == 0:
        return None, 0, 0, 0
    try:
        bs = df["buyorsell"].astype(int)
        vol = df["vol"].astype(float)
        buy = float(vol[bs == 0].sum())
        sell = float(vol[bs == 1].sum())
        tot = buy + sell
        if tot <= 0:
            return None, 0, 0, 0
        return buy / tot, buy, sell, int(len(df))
    except Exception:
        return None, 0, 0, 0


class MootdxFeed(object):
    def __init__(self, out_dir=DEFAULT_OUT_DIR, poll_sec=POLL_SEC,
                 symbols=None):
        self.out_dir = out_dir
        self.poll_sec = poll_sec
        self.symbols = symbols or []
        self.client = None
        self.last_snapshot = {}

    def _get_client(self):
        if self.client is None:
            if Quotes is None:
                raise RuntimeError("mootdx not installed; pip install mootdx")
            self.client = Quotes.factory(market="std", multithread=True)
        return self.client

    def _fetch_one(self, symbol):
        m = _market_code(symbol)
        if not m:
            return None, None
        code, _mkt = m
        client = self._get_client()
        try:
            df = client.transaction(symbol=code)
        except Exception:
            return None, None
        return code, df

    def refresh(self):
        """Poll all symbols, update snapshot, return dict of updates."""
        updates = {}
        for sym in self.symbols:
            code, df = self._fetch_one(sym)
            if code is None:
                continue
            abr, buy, sell, n = _compute_abr(df)
            if abr is None:
                continue
            rec = {
                "abr": round(abr, 4),
                "buy_vol": buy,
                "sell_vol": sell,
                "ts": int(time.time()),
                "n": n,
            }
            self.last_snapshot[sym] = rec
            updates[sym] = rec
        return updates

    def save(self, filename=None):
        if not os.path.isdir(self.out_dir):
            try:
                os.makedirs(self.out_dir)
            except Exception:
                pass
        path = filename or os.path.join(
            self.out_dir,
            time.strftime("%Y%m%d") + ".json",
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.last_snapshot, f, ensure_ascii=False, indent=1)
        return path

    def run_forever(self):
        print("[mootdx_feed] start. symbols=%d poll=%ds out=%s"
              % (len(self.symbols), self.poll_sec, self.out_dir))
        while True:
            try:
                if not _is_trading_time():
                    if self.last_snapshot:
                        print("[mootdx_feed] outside trading hours, keep last "
                              "snapshot")
                    time.sleep(self.poll_sec)
                    continue
                t0 = time.time()
                updates = self.refresh()
                path = self.save()
                print("[mootdx_feed] %s updated=%d ts=%d path=%s"
                      % (time.strftime("%H:%M:%S"), len(updates),
                         int(time.time()), path))
                for sym, rec in sorted(updates.items()):
                    print("   %s abr=%.3f buy=%d sell=%d n=%d"
                          % (sym, rec["abr"], rec["buy_vol"],
                             rec["sell_vol"], rec["n"]))
                el = time.time() - t0
                time.sleep(max(1, self.poll_sec - el))
            except KeyboardInterrupt:
                print("[mootdx_feed] stopped.")
                return
            except Exception as e:
                print("[mootdx_feed] error: %s" % e)
                time.sleep(self.poll_sec)


def main():
    ap = argparse.ArgumentParser(description="mootdx tick feed for Track B")
    ap.add_argument("--symbols", default=None,
                    help="comma-separated symbols, e.g. "
                         "600519.SH,000001.SZ")
    ap.add_argument("--symbols-file", default=None,
                    help="file with one symbol per line / or JSON list")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--poll", type=int, default=POLL_SEC)
    ap.add_argument("--once", action="store_true",
                    help="single poll then exit (for cron/one-shot)")
    args = ap.parse_args()

    symbols = []
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if args.symbols_file:
        with open(args.symbols_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("["):
                    try:
                        symbols = json.loads(line)
                        break
                    except Exception:
                        pass
                else:
                    symbols.append(line)

    feed = MootdxFeed(out_dir=args.out_dir, poll_sec=args.poll,
                      symbols=symbols)
    if args.once:
        updates = feed.refresh()
        path = feed.save()
        print("[mootdx_feed] once done. updated=%d path=%s"
              % (len(updates), path))
        for sym, rec in sorted(updates.items()):
            print("   %s abr=%.3f buy=%d sell=%d n=%d"
                  % (sym, rec["abr"], rec["buy_vol"], rec["sell_vol"],
                     rec["n"]))
        return
    feed.run_forever()


if __name__ == "__main__":
    main()
