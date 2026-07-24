#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan alternative market_severe definitions: frequency + forward index returns."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from market_env_gate import (
    INDEXES,
    _flags_from_indexes,
    _trend_from_klines,
    fetch_all_index_klines,
    position_exposure,
)

ROOT = Path(__file__).resolve().parents[1]


def asof_slice(kl, asof):
    return [x for x in kl if x["date"] <= asof]


def main():
    ih = fetch_all_index_klines(lmt=500)
    sh = ih.get("sh_main") or []
    dates = [x["date"] for x in sh if x["date"] >= "2024-01-01"]
    print("n_dates", len(dates), dates[0], dates[-1])

    rows = []
    for d in dates:
        idxs = {}
        for k in INDEXES:
            st = _trend_from_klines(asof_slice(ih.get(k) or [], d))
            st["name"] = INDEXES[k]["name"]
            idxs[k] = st
        flags = _flags_from_indexes(idxs)
        expo = position_exposure(flags)
        rows.append(
            {
                "date": d,
                "expo": expo,
                "sh3": idxs["sh_main"]["ret_3d"],
                "sh5": idxs["sh_main"]["ret_5d"],
                "sh10": idxs["sh_main"]["ret_10d"],
                "sz3": idxs["sz_main"]["ret_3d"],
                "sz5": idxs["sz_main"]["ret_5d"],
                "sz10": idxs["sz_main"]["ret_10d"],
                "cy5": idxs["chinext"]["ret_5d"],
                "kc5": idxs["star50"]["ret_5d"],
                "m_sev": flags["market_severe"],
                "m_weak": flags["market_weak"],
                "t_sev": flags["tech_severe"],
                "sh_sev": idxs["sh_main"]["severe"],
                "sz_sev": idxs["sz_main"]["severe"],
            }
        )
    df = pd.DataFrame(rows)
    print("expo counts:\n", df["expo"].value_counts().sort_index())
    print(
        "severe",
        int(df.m_sev.sum()),
        f"{100 * df.m_sev.mean():.2f}%",
        "weak",
        int(df.m_weak.sum()),
        f"{100 * df.m_weak.mean():.2f}%",
        "tech_sev",
        int(df.t_sev.sum()),
        f"{100 * df.t_sev.mean():.2f}%",
    )
    print("SH5 pctl", df.sh5.quantile([0.01, 0.05, 0.1, 0.2, 0.5]).to_dict())
    print("SZ5 pctl", df.sz5.quantile([0.01, 0.05, 0.1, 0.2, 0.5]).to_dict())
    mn = df[["sh5", "sz5"]].min(axis=1)
    print("min(SH5,SZ5) pctl", mn.quantile([0.01, 0.05, 0.1, 0.2]).to_dict())

    avg5 = (df.sh5 + df.sz5) / 2
    rules = {
        "CUR_both_severe": df.m_sev,
        "A_both5le4_10le25": (df.sh5 <= -4) & (df.sh10 <= -2.5) & (df.sz5 <= -4) & (df.sz10 <= -2.5),
        "B_both5le35": (df.sh5 <= -3.5) & (df.sz5 <= -3.5),
        "C_either_board_sev": df.sh_sev | df.sz_sev,
        "D_avg5le4_bothle2": (avg5 <= -4) & (df.sh5 <= -2) & (df.sz5 <= -2),
        "E_fast_both3le3_5le3": (df.sh3 <= -3) & (df.sz3 <= -3) & (df.sh5 <= -3) & (df.sz5 <= -3),
        "F_cur_or_avg5le5": df.m_sev | (avg5 <= -5),
        "G_cur_and_avg5le6": df.m_sev & (avg5 <= -6),
        "H_soft_weak_avg5le35": df.m_weak & (avg5 <= -3.5),
        # proposed ladder pieces
        "P_hard_avg5le6_or_cur": (avg5 <= -6) | df.m_sev,
        "P_soft_avg5le4_not_hard": (avg5 <= -4) & (df.sh5 <= -2.5) & (df.sz5 <= -2.5) & ~((avg5 <= -6) | df.m_sev),
    }

    sh_map = {x["date"]: x["change_pct"] for x in sh}
    print("\n=== rule freq + forward SH ===")
    scan = {}
    for name, mask in rules.items():
        n = int(mask.sum())
        last = list(df.loc[mask, "date"].tail(8))
        f1, f5 = [], []
        for d in df.loc[mask, "date"]:
            i = dates.index(d)
            if i + 1 < len(dates):
                f1.append(sh_map[dates[i + 1]])
            if i + 5 < len(dates):
                f5.append(sum(sh_map[dates[j]] for j in range(i + 1, i + 6)))
        row = {
            "n": n,
            "pct": round(100 * n / len(df), 2),
            "last": last,
            "fwd1_mean": None if not f1 else round(float(np.mean(f1)), 3),
            "fwd1_up_pct": None if not f1 else round(100 * float(np.mean(np.array(f1) > 0)), 1),
            "fwd5_mean": None if not f5 else round(float(np.mean(f5)), 3),
        }
        scan[name] = row
        print(
            f"{name}: n={n} ({row['pct']}%) fwd1={row['fwd1_mean']}% "
            f"up={row['fwd1_up_pct']}% fwd5={row['fwd5_mean']}% last={last[-4:]}"
        )

    print("\nCUR severe detail:")
    print(
        df.loc[
            df.m_sev,
            ["date", "sh3", "sh5", "sh10", "sz3", "sz5", "sz10", "cy5", "kc5", "expo"],
        ].to_string(index=False)
    )

    # overlap: days that are weak but NOT severe — candidate for soft sleeve / 0.25
    soft = df.m_weak & ~df.m_sev
    print(f"\nweak_not_severe: {int(soft.sum())} ({100*soft.mean():.1f}%)")

    out = {
        "window": [dates[0], dates[-1]],
        "n": len(df),
        "current_counts": {
            "severe_n": int(df.m_sev.sum()),
            "weak_n": int(df.m_weak.sum()),
            "expo0_n": int((df.expo == 0).sum()),
            "expo05_n": int((df.expo == 0.5).sum()),
            "expo1_n": int((df.expo == 1).sum()),
        },
        "sh5_pct": {str(k): float(v) for k, v in df.sh5.quantile([0.01, 0.05, 0.1, 0.2]).items()},
        "sz5_pct": {str(k): float(v) for k, v in df.sz5.quantile([0.01, 0.05, 0.1, 0.2]).items()},
        "rules": scan,
        "proposal_note": "Prefer ladder expo 1/0.5/0.25/0 over binary empty; hard empty rarer than soft cut.",
    }
    path = ROOT / "output/severe_threshold_scan.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", path)


if __name__ == "__main__":
    main()
