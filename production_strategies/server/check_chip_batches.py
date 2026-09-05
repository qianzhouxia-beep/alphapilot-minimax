#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chip 上传批次完整性校验（2026-08-24 根治）

生产 chip_data_all.json 由 WorkBuddy 本地拉东财真实 CYQ 筹码 → 批次文件
`_chip_batch_{NN}_{YYYYMMDD}.json` → `_upload_chip_{YYYYMMDD}.py` 合并上传。

08-24 事故：批次缺 18/19 两个（400 只）仍照常上传 → 服务器保留 1192 只旧数据
停在 08-21，无人察觉。本工具在**上传前**校验批次完整性：

  1. 预期批次号 00~N 连续（缺号即告警）
  2. 总覆盖股票数 >= MIN_COVER 阈值（默认 4850，全市场约 4991）
  3. 合并后的最新日期应等于目标日期

用法（在 _chip_batch_*_{date}.json 所在目录执行）:
  python check_chip_batches.py --date 2026-08-24 [--min-cover 4850] [--json]

退出码: 0=通过可上传；1=缺批次/覆盖率不足，禁止上传；2=其他错误
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

DEFAULT_MIN_COVER = 4850  # 全市场约 4991，留 ~3% 新股/停牌余量


def collect_batches(date: str, root: str | Path) -> dict:
    """返回 {batch_idx: Path} 与批次数。date 支持 20260824 或 0824 两种后缀。"""
    root = Path(root)
    date_suffix = date.replace("-", "")
    if date_suffix.startswith("20"):
        date_suffix = date_suffix[-4:]  # 20260824 -> 0824
    pat = root / f"_chip_batch_*_{date_suffix}.json"
    files = sorted(glob.glob(str(pat)))
    out: dict[int, Path] = {}
    for fn in files:
        name = Path(fn).name
        # _chip_batch_18_0824.json -> 18
        try:
            idx = int(name.replace(f"_chip_batch_", "").replace(f"_{date_suffix}.json", ""))
        except ValueError:
            continue
        out[idx] = Path(fn)
    return out


def verify(date: str, root: str | Path, min_cover: int) -> dict:
    batches = collect_batches(date, root)
    result = {
        "date": date,
        "n_batches": len(batches),
        "batch_indices": sorted(batches),
        "missing_indices": [],
        "n_symbols": 0,
        "min_cover": min_cover,
        "ok": False,
        "issues": [],
        "dates": [],
    }
    if not batches:
        result["issues"].append(f"未找到任何批次文件 _chip_batch_*_{date}.json")
        return result

    idxs = sorted(batches)
    # 1. 连续性检查
    if idxs != list(range(idxs[0], idxs[-1] + 1)):
        missing = [i for i in range(idxs[0], idxs[-1] + 1) if i not in set(idxs)]
        result["missing_indices"] = missing
        result["issues"].append(
            f"批次号不连续，缺失: {missing}。缺 {len(missing)} 批 ×200 ≈ {len(missing)*200} 只可能漏传"
        )

    # 2. 覆盖率检查
    merged: dict[str, object] = {}
    for idx in idxs:
        try:
            d = json.loads(batches[idx].read_text(encoding="utf-8"))
            data = d.get("data", d) if isinstance(d, dict) else d
            for code, v in data.items():
                merged[code[-6:]] = v
        except Exception as e:
            result["issues"].append(f"批次 {idx} 读取失败: {e}")
    result["n_symbols"] = len(merged)
    if len(merged) < min_cover:
        result["issues"].append(
            f"总覆盖 {len(merged)} 只 < {min_cover}，覆盖率不足，禁止上传"
        )

    # 3. 日期检查
    dates = {
        str(v.get("date"))[:10]
        for v in merged.values()
        if isinstance(v, dict) and v.get("date")
    }
    result["dates"] = sorted(dates)
    target_hyphen = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    if result["dates"] and result["dates"][-1] != target_hyphen:
        result["issues"].append(
            f"最新日期 {result['dates'][-1]} != 目标 {target_hyphen}，数据可能不是当日批次"
        )

    result["ok"] = len(result["issues"]) == 0
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="目标日期 YYYY-MM-DD 或 YYYYMMDD")
    ap.add_argument("--min-cover", type=int, default=DEFAULT_MIN_COVER)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dir", default=".", help="批次文件所在目录")
    args = ap.parse_args()

    date = args.date.replace("-", "")
    res = verify(date, args.dir, args.min_cover)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"chip 批次校验 {args.date}:")
        print(f"  批次: {res['n_batches']} 个, 序号 {res['batch_indices']}")
        if res["missing_indices"]:
            print(f"  ❌ 缺失批次: {res['missing_indices']}")
        print(f"  覆盖: {res['n_symbols']} 只 (阈值 {res['min_cover']})")
        print(f"  日期: {res['dates']}")
        for it in res["issues"]:
            print(f"  ❌ {it}")
        print("  结果:", "✅ 通过，可上传" if res["ok"] else "❌ 不通过，禁止上传")

    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
