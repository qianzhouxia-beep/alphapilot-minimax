# -*- coding: utf-8 -*-
"""构建"多时点板块热度快照"缓存 v6 —— 跳过非个股 + worker写临时文件。
"""
import os, glob, json
import pandas as pd
from multiprocessing import Pool

K5M = r"D:\alphapilot\data\kline5m_full"
IND = r"C:\Users\elvisq\Projects\alphapilot\data\stock_industry_map.json"
OUT = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_board_snap_cache.parquet"
TMP = r"C:\Users\elvisq\Projects\alphapilot\bt_research\_snap_tmp"

# 9:35=5 ... 11:30=120, 13:30=240, 15:00=330
SNAPS = [5, 10, 15, 20, 25, 30, 60, 90, 120, 240, 330]
W0, W1 = "2026-04-01", "2026-07-31"

def process(args):
    fi, sym2l3, out_i = args
    sym = os.path.basename(fi).replace(".parquet", "")
    if not sym2l3.get(sym):
        return None
    l3 = sym2l3[sym]
    try:
        df = pd.read_parquet(fi, columns=["date", "time", "open", "high", "low", "close", "amount", "volume"])
    except Exception:
        return None
    if df.empty:
        return None
    t = df["time"].str.split(":", expand=True)
    df["min"] = (t[0].astype(int) - 9) * 60 + (t[1].astype(int) - 30)
    df = df.sort_values(["date", "min"])
    df["cum_amount"] = df.groupby("date")["amount"].cumsum()
    df["cum_volume"] = df.groupby("date")["volume"].cumsum()
    sel = df[df["min"].isin(SNAPS)]
    if sel.empty:
        return None
    sel = sel[(sel["date"] >= W0) & (sel["date"] <= W1)]
    if sel.empty:
        return None
    sel["symbol"] = sym
    sel["industry_l3"] = l3
    out = sel[["date", "symbol", "industry_l3", "min", "open", "high", "low", "close",
               "cum_amount", "cum_volume"]].rename(columns={"min": "snap_min"})
    op = os.path.join(TMP, f"{out_i:05d}.parquet")
    out.to_parquet(op)
    return op

def main():
    ind = json.load(open(IND, encoding="utf-8"))
    sym2l3 = {s: info.get("industry_l3") or "" for s, info in ind.items()}
    files = glob.glob(os.path.join(K5M, "*.parquet"))
    print("files:", len(files))
    os.makedirs(TMP, exist_ok=True)
    args = [(fi, sym2l3, i) for i, fi in enumerate(files)]
    paths = []
    with Pool(processes=8) as pool:
        for i, p in enumerate(pool.imap_unordered(process, args, chunksize=64)):
            if p:
                paths.append(p)
            if (i + 1) % 2000 == 0:
                print(f"  {i+1}/{len(files)}", flush=True)
    print("tmp files:", len(paths), flush=True)
    outs = [pd.read_parquet(p) for p in paths]
    out = pd.concat(outs, ignore_index=True)
    out.to_parquet(OUT)
    print("done. rows:", len(out))
    print(out.groupby("snap_min").size().to_string())

if __name__ == "__main__":
    main()
