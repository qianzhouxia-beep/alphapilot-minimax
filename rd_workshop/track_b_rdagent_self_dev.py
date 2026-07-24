#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Track B — RD-Agent 自研因子开发（独立于当前 Production Model 结构）。

本轨道在 Workshop 内跑 RD-Agent(Q) / 导入其导出因子，再经晋升适配器做
candidate train_v25 + 可交易 OOS。不嵌入生产 Task Chain。

用法:
  # 仅检查环境 + 打印 RD-Agent 建议命令
  python3 -u rd_workshop/track_b_rdagent_self_dev.py --doctor

  # 已有 RD-Agent 导出因子 → 归一化 → 晋升适配器
  python3 -u rd_workshop/track_b_rdagent_self_dev.py --from-export path/to/factors.parquet --promote

  # 若已安装 rdagent CLI，尝试拉起 fin_quant（仍不写生产）
  python3 -u rd_workshop/track_b_rdagent_self_dev.py --run-rdagent --evolving-n 5
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT / "rd_workshop"
INBOUND = WS / "data_support" / "inbound"
RDAGENT_WORK = WS / "rdagent_runs"
TRACK = "track_b_rdagent_self_dev"


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def doctor() -> dict:
    info = {
        "track": TRACK,
        "rdagent_cli": _which("rdagent"),
        "python": sys.executable,
        "inbound": str(INBOUND),
        "rdagent_work": str(RDAGENT_WORK),
        "qlib_data_hint": str(Path.home() / ".qlib" / "qlib_data" / "cn_data"),
        "notes": [
            "Install: pip install rdagent  (Python 3.10/3.11)",
            "Docs: https://rdagent.readthedocs.io/en/latest/scens/quant_agent_fin.html",
            "Run loop: rdagent fin_quant",
            "Export factors to parquet/csv then --from-export ... --promote",
            "Never point RD-Agent output at production models/",
        ],
    }
    try:
        import importlib.util

        info["rdagent_importable"] = importlib.util.find_spec("rdagent") is not None
    except Exception:
        info["rdagent_importable"] = False
    return info


def run_rdagent(evolving_n: int) -> int:
    cli = _which("rdagent")
    if not cli:
        print("rdagent CLI not found. pip install rdagent 后重试，或改用 --from-export")
        print(json.dumps(doctor(), ensure_ascii=False, indent=2))
        return 2
    RDAGENT_WORK.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["QLIB_QUANT_evolving_n"] = str(evolving_n)
    # 工作目录隔离在车间
    log = RDAGENT_WORK / f"fin_quant_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    cmd = [cli, "fin_quant"]
    print("RUN:", " ".join(cmd), flush=True)
    print(f"log -> {log}", flush=True)
    with log.open("w", encoding="utf-8") as f:
        rc = subprocess.call(cmd, cwd=str(RDAGENT_WORK), env=env, stdout=f, stderr=subprocess.STDOUT)
    print(f"rdagent exit={rc}; inspect {RDAGENT_WORK} for factor exports, then --from-export")
    return rc


def promote_from_export(path: Path, max_stocks: int, skip_oos: bool) -> int:
    if not path.exists():
        raise SystemExit(f"export not found: {path}")
    INBOUND.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    staged = INBOUND / f"{TRACK}_raw_{stamp}{path.suffix.lower() or '.parquet'}"
    shutil.copy2(path, staged)
    meta = {
        "track": TRACK,
        "staged_at": stamp,
        "source": str(path),
        "staged": str(staged),
    }
    (INBOUND / f"{TRACK}_meta_{stamp}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cmd = [
        sys.executable,
        "-u",
        str(WS / "run_promotion_adapter.py"),
        "--factors",
        str(staged),
        "--run-id",
        f"{TRACK}_{stamp}",
    ]
    if max_stocks:
        cmd.extend(["--max-stocks", str(max_stocks)])
    if skip_oos:
        cmd.append("--skip-oos")
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Track B: RD-Agent self-developed factors")
    ap.add_argument("--doctor", action="store_true")
    ap.add_argument("--run-rdagent", action="store_true", help="invoke `rdagent fin_quant` if installed")
    ap.add_argument("--evolving-n", type=int, default=5)
    ap.add_argument("--from-export", default="", help="RD-Agent / Qlib factor file to promote")
    ap.add_argument("--promote", action="store_true", help="with --from-export, run promotion adapter")
    ap.add_argument("--max-stocks", type=int, default=0)
    ap.add_argument("--skip-oos", action="store_true")
    args = ap.parse_args()

    print(f"=== {TRACK} ===", flush=True)

    if args.doctor or (
        not args.run_rdagent and not args.from_export
    ):
        print(json.dumps(doctor(), ensure_ascii=False, indent=2))
        if not args.run_rdagent and not args.from_export:
            return 0

    rc = 0
    if args.run_rdagent:
        rc = run_rdagent(args.evolving_n)
        if rc != 0:
            return rc

    if args.from_export:
        path = Path(args.from_export)
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if args.promote or True:
            # from-export 的默认动作就是进晋升闸门（Workshop 出口）
            return promote_from_export(path, args.max_stocks, args.skip_oos)

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
