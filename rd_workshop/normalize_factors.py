#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RD-Workshop：因子表归一化与对齐（Data Support 入口）。

支持输入形态（任选其一）:
  1) AlphaPilot 宽表: date, symbol|code, f1, f2, ...
  2) Qlib/RD-Agent MultiIndex: (datetime, instrument) × factors
  3) 长表: date, symbol, factor, value

输出标准宽表 parquet:
  date (YYYY-MM-DD), symbol (6 位), rd_* 因子列
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def bare_code(sym) -> str:
    s = str(sym or "").strip().upper()
    s = s.replace("SH", "").replace("SZ", "").replace("BJ", "")
    if "." in s:
        s = s.split(".")[0]
    digits = re.sub(r"\D", "", s)
    return digits.zfill(6)[-6:] if digits else ""


def _safe_factor_name(name: str) -> str:
    n = re.sub(r"[^\w]+", "_", str(name).strip(), flags=re.UNICODE)
    n = n.strip("_").lower() or "f"
    if not n.startswith("rd_"):
        n = "rd_" + n
    return n[:64]


def _pick_col(cols, candidates: list[str]) -> str | None:
    lower = {str(c).lower(): c for c in cols}
    for c in candidates:
        if c in lower:
            return lower[c]
    return None


def normalize_factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    """任意常见形态 → date/symbol/rd_* 宽表。"""
    if df is None or len(df) == 0:
        raise ValueError("empty factor frame")

    # MultiIndex (datetime, instrument)
    if isinstance(df.index, pd.MultiIndex) and df.index.nlevels >= 2:
        df = df.reset_index()
        # after reset, level names become columns
        cols = list(df.columns)
        # heuristic: first two cols are date / instrument if unnamed
        if "date" not in [str(c).lower() for c in cols]:
            df = df.rename(columns={cols[0]: "date", cols[1]: "symbol"})

    # Long format
    factor_col = _pick_col(df.columns, ["factor", "factor_name", "name", "field"])
    value_col = _pick_col(df.columns, ["value", "val", "factor_value", "v"])
    if factor_col and value_col:
        date_col = _pick_col(df.columns, ["date", "datetime", "dt", "trade_date"])
        sym_col = _pick_col(df.columns, ["symbol", "code", "instrument", "windcode", "ticker"])
        if not date_col or not sym_col:
            raise ValueError("long format needs date + symbol columns")
        tmp = df[[date_col, sym_col, factor_col, value_col]].copy()
        tmp.columns = ["date", "symbol", "factor", "value"]
        tmp["date"] = tmp["date"].astype(str).str[:10]
        tmp["symbol"] = tmp["symbol"].map(bare_code)
        tmp["factor"] = tmp["factor"].map(_safe_factor_name)
        wide = tmp.pivot_table(
            index=["date", "symbol"], columns="factor", values="value", aggfunc="last"
        )
        wide = wide.reset_index()
        return _finalize_wide(wide)

    # Wide format
    date_col = _pick_col(df.columns, ["date", "datetime", "dt", "trade_date"])
    sym_col = _pick_col(df.columns, ["symbol", "code", "instrument", "windcode", "ticker"])
    if not date_col or not sym_col:
        raise ValueError("wide format needs date + symbol/code/instrument columns")
    out = df.copy()
    out = out.rename(columns={date_col: "date", sym_col: "symbol"})
    out["date"] = out["date"].astype(str).str[:10]
    out["symbol"] = out["symbol"].map(bare_code)
    return _finalize_wide(out)


def _finalize_wide(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["symbol"].astype(str).str.len() == 6].copy()
    rename = {}
    factor_cols = []
    for c in df.columns:
        if c in ("date", "symbol"):
            continue
        nn = _safe_factor_name(c)
        rename[c] = nn
        factor_cols.append(nn)
    df = df.rename(columns=rename)
    # dedupe columns
    df = df.loc[:, ~df.columns.duplicated()]
    keep = ["date", "symbol"] + [c for c in factor_cols if c in df.columns]
    df = df[keep]
    for c in keep[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["date", "symbol"])
    df = df.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"], keep="last")
    if len(keep) <= 2:
        raise ValueError("no factor columns after normalize")
    return df.reset_index(drop=True)


def load_and_normalize(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() in (".parquet", ".pq"):
        raw = pd.read_parquet(path)
    elif path.suffix.lower() in (".csv", ".txt"):
        raw = pd.read_csv(path)
    elif path.suffix.lower() in (".pkl", ".pickle"):
        raw = pd.read_pickle(path)
    else:
        raise ValueError(f"unsupported factor file: {path}")
    return normalize_factor_frame(raw)


def merge_extra_factors(
    feats: pd.DataFrame, symbol: str, extra: pd.DataFrame | None, factor_cols: list[str]
) -> pd.DataFrame:
    """按 date 左连接额外因子；缺列补 0。"""
    if feats is None:
        return feats
    out = feats.copy()
    if "date" not in out.columns:
        for c in factor_cols:
            out[c] = 0.0
        return out
    out["date"] = out["date"].astype(str).str[:10]
    code = bare_code(symbol)
    if extra is None or not factor_cols:
        for c in factor_cols:
            if c not in out.columns:
                out[c] = 0.0
        return out
    sub = extra.loc[extra["symbol"] == code, ["date"] + factor_cols]
    if sub.empty:
        for c in factor_cols:
            out[c] = 0.0
        return out
    out = out.merge(sub, on="date", how="left", suffixes=("", "_rd"))
    for c in factor_cols:
        if c not in out.columns:
            alt = f"{c}_rd"
            out[c] = out[alt] if alt in out.columns else 0.0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize RD-Agent / Qlib factors for AlphaPilot")
    ap.add_argument("--input", required=True, help="raw factor parquet/csv/pkl")
    ap.add_argument(
        "--output",
        default="",
        help="output parquet (default: rd_workshop/data_support/inbound/normalized_factors.parquet)",
    )
    args = ap.parse_args()
    out = Path(args.output) if args.output else (
        ROOT / "rd_workshop" / "data_support" / "inbound" / "normalized_factors.parquet"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    df = load_and_normalize(Path(args.input))
    df.to_parquet(out, index=False)
    cols = [c for c in df.columns if c not in ("date", "symbol")]
    print(f"OK rows={len(df)} symbols={df['symbol'].nunique()} factors={len(cols)}")
    print(f"factors: {', '.join(cols[:20])}{'...' if len(cols) > 20 else ''}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
