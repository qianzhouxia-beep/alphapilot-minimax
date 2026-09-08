#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日滚动窗口模型重训（独立 cron，21:30 运行）。

设计动机（2026-08-08 修复）：
  - 原 16:15 feedback_loop 内嵌重训存在 4 个缺陷：
    1) 数据滞后一天：16:15 时当天资金流 21:00 才入库 → 重训用昨天数据
    2) 超时余量不足：训练 ~1060s，上限 1200s，16:15 又叠加 fix_kline_server /
       feedback_auto_tune / rebuild_backtest_cache 等 cron 抢 CPU → 频繁 timeout
    3) 失败记录被吞：TimeoutExpired 分支不写日志，掩盖失败
    4) 半成品风险：train_ensemble 先写 base 再写 opt，opt 写到一半超时 → 混合模型
  本脚本改为 21:30 独立运行（资金流 21:00 + RD因子 21:20 均就绪），
  训练到临时目录，全部成功后原子替换，失败自动回滚，状态落盘便于巡检。

AUC 安全门（2026-08-08 追加）：
  - 验证集 AUC 有噪声（相邻两日全样本波动可达 ±0.005），若要求"必须不下降"，
    噪声会误拒"更新数据但 AUC 略低"的模型。
  - 故采用容忍区间：新 AUC >= 旧 AUC - --auc-tolerance（默认 0.003）→ 替换
    （数据新鲜本身是价值）；下降超容忍才拒绝替换，保留旧模型。
  - --max-stocks 仅用于 smoke 测试（test 模式）：绝不写生产/替换/备份。

用法:
  python3 scripts/run_daily_retrain.py [--timeout 3600] [--max-stocks N] [--auc-tolerance 0.003]

产出:
  output/feedback/retrain_status.json   ← 巡检读这个（含 auc_gate 判定）
  output/logs/train_v25_retrain.log     ← 完整日志
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

MODELS = ROOT / "models"
TMP = ROOT / "models" / ".retrain_tmp"
STATUS = ROOT / "output" / "feedback" / "retrain_status.json"
LOG = ROOT / "output" / "logs" / "train_v25_retrain.log"
BACKUP_DIR = ROOT / "output" / "feedback" / "retrain_backup"

# 生产只用 opt（106维）；base 也备份，便于失败回滚到完整旧版
V25_FILES = ["v25_meta.json", "best_tech_params.json"]
V25_FILES += [f"v25_base_ensemble_{i}.ubj" for i in (1, 2, 3)]
V25_FILES += [f"v25_opt_ensemble_{i}.ubj" for i in (1, 2, 3)]

# AUC 安全门：新模型 AUC 相对旧模型允许的最大下降容忍。
# 验证集 AUC 本身有噪声（历史观测：相邻两天全样本 AUC 波动可达 ±0.005），
# 若要求"必须不下降"，噪声就会误拒更新数据的模型。故采用容忍区间：
#   新 AUC >= 旧 AUC - AUC_TOLERANCE → 替换（数据新鲜本身是价值）
#   新 AUC <  旧 AUC - AUC_TOLERANCE → 拒绝（明显退化才拦）
# 该值可按需通过 --auc-tolerance 调整。
AUC_TOLERANCE_DEFAULT = 0.003


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _log(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


def backup_current() -> Path:
    """把现有 v25 生产文件备份到 retrain_backup/<ts>/。返回备份目录。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = BACKUP_DIR / ts
    bak.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in V25_FILES:
        src = MODELS / f
        if src.exists():
            shutil.copy2(src, bak / f)
            n += 1
    _log(f"已备份 {n} 个生产模型文件 → {bak}")
    return bak


def restore_backup(bak: Path) -> None:
    """从备份恢复（重训失败/超时时调用），保证生产模型不被半成品污染。"""
    restored = 0
    for f in bak.iterdir():
        dst = MODELS / f.name
        shutil.copy2(f, dst)
        restored += 1
    _log(f"⚠️ 已回滚 {restored} 个文件 ← {bak}（保留旧生产模型）")


def write_status(d: dict) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_opt_auc(meta_path: Path) -> float | None:
    """从 v25_meta.json 读 v25_opt AUC；无则返回 None。"""
    try:
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        ab = m.get("ab_test") or {}
        if isinstance(ab, dict):
            v = ab.get("v25_opt_auc")
            if isinstance(v, (int, float)):
                return float(v)
    except Exception:
        pass
    return None


def auc_gate_passed(new_auc: float | None, old_auc: float | None,
                    tolerance: float) -> tuple[bool, str]:
    """AUC 安全门：新模型 AUC 不得低于旧模型 AUC 超过 tolerance。

    语义：验证集 AUC 有噪声，tolerance 为"允许的最大下降"，
    在容忍区间内的下降仍替换（因新模型数据更新鲜）；
    只有明显退化（下降超 tolerance）才拒绝替换，保留旧模型。
    任何一侧 AUC 缺失 → 保守拒绝（除首次部署旧缺失时直接采用）。
    """
    if new_auc is None:
        return False, "新模型 AUC 缺失（meta 未含 v25_opt_auc）→ 保守拒绝替换"
    if old_auc is None:
        return True, f"旧模型 AUC 缺失（首次部署），直接采用新模型 AUC={new_auc:.4f}"
    diff = new_auc - old_auc
    if diff < -tolerance - 1e-9:
        return False, (
            f"AUC 门未通过: 新={new_auc:.4f} 旧={old_auc:.4f} "
            f"diff={diff:+.4f} 下降超容忍 {-tolerance:.4f} → 拒绝替换，保留旧模型"
        )
    return True, f"AUC 门通过: 新={new_auc:.4f} 旧={old_auc:.4f} diff={diff:+.4f}（容忍 {tolerance:.4f}）"


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="每日滚动窗口模型重训（21:30 独立 cron）")
    ap.add_argument("--timeout", type=int, default=3600, help="训练超时秒数（默认 3600）")
    ap.add_argument("--max-stocks", type=int, default=0, help="smoke 限股票数（0=全量）")
    ap.add_argument(
        "--auc-tolerance",
        type=float,
        default=AUC_TOLERANCE_DEFAULT,
        help="新模型相对旧模型 AUC 允许的最大下降（默认 0.003）；下降超此才拒绝替换",
    )
    args = ap.parse_args()

    # 安全：--max-stocks 仅用于 smoke 测试，禁止写生产/替换。
    test_mode = args.max_stocks is not None and args.max_stocks > 0

    # 防止上次残留临时目录
    if TMP.exists():
        shutil.rmtree(TMP, ignore_errors=True)

    # smoke 测试不备份、不触碰生产；仅生产模式才备份旧模型
    bak = backup_current() if not test_mode else None
    t0 = time.time()
    status = {"started_at": _now(), "ok": False, "rc": None, "duration_s": None,
              "error": None, "trained_at": None, "mode": "test" if test_mode else "production"}

    cmd = [sys.executable or "python3", "-u", str(ROOT / "train_v25.py"),
           "--model-dir", str(TMP)]
    if args.max_stocks and args.max_stocks > 0:
        cmd += ["--max-stocks", str(args.max_stocks)]

    _log(f"启动滚动窗口重训 → 临时目录 {TMP} (timeout={args.timeout}s)")
    try:
        rc = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=args.timeout, cwd=str(ROOT))
        elapsed = round(time.time() - t0, 1)
        status["rc"] = rc.returncode
        status["duration_s"] = elapsed
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text(
            f"=== train_v25 retrain @ {_now()} ===\n"
            f"rc={rc.returncode} elapsed={elapsed}s timeout={args.timeout}s\n"
            f"--- stdout ---\n{rc.stdout}\n--- stderr ---\n{rc.stderr}\n",
            encoding="utf-8",
        )

        if rc.returncode != 0:
            status["error"] = f"train rc={rc.returncode}"
            if bak:
                restore_backup(bak)
            write_status(status)
            _log(f"❌ 重训失败 rc={rc.returncode} ({elapsed}s)，已回滚生产模型")
            return rc.returncode

        # 成功：校验 opt ensemble 3 个文件齐全
        missing = [f for i in (1, 2, 3)
                   if not (TMP / f"v25_opt_ensemble_{i}.ubj").exists()]
        if missing:
            status["error"] = f"opt ensemble 缺失: {missing}"
            if bak:
                restore_backup(bak)
            write_status(status)
            _log(f"❌ opt ensemble 不完整 {missing}，已回滚")
            return 1

        # ── AUC 安全门：新模型 AUC 不得明显低于旧模型才替换 ──
        new_auc = _read_opt_auc(TMP / "v25_meta.json")
        old_auc = _read_opt_auc(MODELS / "v25_meta.json")
        gate_ok, gate_note = auc_gate_passed(new_auc, old_auc, args.auc_tolerance)
        status["auc_gate"] = {
            "passed": gate_ok,
            "new_auc": new_auc,
            "old_auc": old_auc,
            "tolerance": args.auc_tolerance,
            "note": gate_note,
        }

        if test_mode:
            # smoke 测试：只报告 AUC 结论，绝不替换生产
            shutil.rmtree(TMP, ignore_errors=True)
            status["ok"] = True
            status["mode"] = "test"
            status["error"] = None
            status["trained_at"] = None
            status["swapped"] = []
            write_status(status)
            _log(f"🔬 [TEST] 训练完成 new_auc={new_auc if new_auc is not None else 'NA'} "
                 f"(vs 生产 {old_auc if old_auc is not None else 'NA'}) → {gate_note}；"
                 f"smoke 模式不替换生产")
            return 0

        if not gate_ok:
            # 不替换：清临时目录，保留旧生产模型，状态落盘
            shutil.rmtree(TMP, ignore_errors=True)
            status["ok"] = False
            status["error"] = "auc_gate_rejected"
            status["trained_at"] = None
            write_status(status)
            _log(f"⛔ AUC 安全门拒绝替换：{gate_note}（生产模型保持旧版）")
            return 0

        # 原子替换：把 tmp 中 v25 相关文件全部拷回生产 models/
        swapped = []
        for f in TMP.iterdir():
            if f.name in V25_FILES or f.name.startswith("extra_factors"):
                shutil.copy2(f, MODELS / f.name)
                swapped.append(f.name)
        # 清理临时目录
        shutil.rmtree(TMP, ignore_errors=True)

        # 解析 meta 里 trained_at / AUC
        trained_at = None
        meta = {}
        meta_path = MODELS / "v25_meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                trained_at = meta.get("trained_at")
            except Exception:
                pass
        status["ok"] = True
        status["trained_at"] = trained_at
        status["swapped"] = swapped
        status["auc"] = meta.get("ab_test", {}).get("v25_opt_auc") if isinstance(meta.get("ab_test"), dict) else None
        write_status(status)

        _log(f"✅ 重训成功 ({elapsed}s) → 已替换 {len(swapped)} 个生产文件 | trained_at={trained_at} | {gate_note}")
        # 清理旧备份（保留最近 7 份）
        backups = sorted(BACKUP_DIR.iterdir()) if BACKUP_DIR.exists() else []
        for old in backups[:-7]:
            shutil.rmtree(old, ignore_errors=True)
        return 0

    except subprocess.TimeoutExpired as te:
        elapsed = round(time.time() - t0, 1)
        status["duration_s"] = elapsed
        status["error"] = f"timeout_{args.timeout}s"
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text(
            f"=== train_v25 retrain @ {_now()} ===\n"
            f"TIMEOUT {args.timeout}s elapsed={elapsed}s\n"
            f"--- stderr tail ---\n{(te.stderr or '')[-2000:]}\n",
            encoding="utf-8",
        )
        if bak:
            restore_backup(bak)
        write_status(status)
        _log(f"❌ 重训超时（>{args.timeout}s），已回滚生产模型")
        return 1
    except Exception as e:
        status["error"] = str(e)
        if bak:
            try:
                restore_backup(bak)
            except Exception:
                pass
        write_status(status)
        _log(f"❌ 重训异常: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
