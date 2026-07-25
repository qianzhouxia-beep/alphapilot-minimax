#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集合竞价因子全流程执行脚本
=============================
在远程服务器上运行：
  1. 前置检查 - 确认代码已同步、数据就绪
  2. ICIR 分析 - 计算集合竞价因子各项 IC/ICIR
  3. 全量重训 - 含新因子的 VM2.5 XGBoost 模型
  4. 回测对比 - 新旧模型 A/B 对比
  5. 报告生成 - 汇总训练结果

用法:
  python3 scripts/run_auction_training.py                  # 完整流程（需 ~2 小时全市场训练）
  python3 scripts/run_auction_training.py --icir-only      # 只跑 ICIR 分析（快速）
  python3 scripts/run_auction_training.py --sample 500     # 小样本快速验证
"""
import os, sys, json, time, subprocess, shutil
from pathlib import Path
from datetime import datetime

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
os.chdir(str(ROOT))
sys.path.insert(0, str(ROOT))

MODEL_DIR = ROOT / "models"
AUCTION_DIR = ROOT / "output" / "auction_eval"
AUCTION_DIR.mkdir(parents=True, exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def run(cmd, timeout_min=120):
    log(f"Running: {cmd}")
    t0 = time.time()
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_min * 60)
    elapsed = time.time() - t0
    if r.returncode != 0:
        log(f"  FAILED (rc={r.returncode}, {elapsed:.0f}s)")
        log(f"  stderr: {r.stderr[-500:]}")
        return False, r
    log(f"  OK ({elapsed:.0f}s)")
    return True, r

def check_prerequisites():
    """确认服务器环境就绪"""
    log("=" * 60)
    log("Step 0: 前置检查")
    log("=" * 60)

    checks = []

    # 1. 集合竞价因子模块
    try:
        from call_auction_factors import ALL_FACTORS, compute_auction_factors
        checks.append(("集合竞价因子模块", True, f"{len(ALL_FACTORS)} 个因子"))
    except Exception as e:
        checks.append(("集合竞价因子模块", False, str(e)))

    # 2. features_v2 集成
    try:
        from features_v2 import build_full_features_v2, V11_FEATURE_COLUMNS
        au_cols = [c for c in V11_FEATURE_COLUMNS if c.startswith("rd_auction")]
        checks.append(("features_v2 集成", True, f"{len(au_cols)} 个竞价因子列注册"))
    except Exception as e:
        checks.append(("features_v2 集成", False, str(e)))

    # 3. K线缓存
    kf = ROOT / "data" / "kline_cache" / "kline_all.parquet"
    if kf.exists():
        import pandas as pd
        kdf = pd.read_parquet(kf)
        n_stocks = kdf["symbol"].nunique()
        checks.append(("K线缓存", True, f"{len(kdf)} 行, {n_stocks} 只"))
    else:
        checks.append(("K线缓存", False, "不存在"))

    # 4. 侧车数据
    for name, path in [
        ("资金流向", "data/fund_flow_history.json"),
        ("融资融券", "data/margin_data.json"),
        ("业绩预告", "data/event_forecast.json"),
        ("筹码", "data/chip_data_all.json"),
    ]:
        p = ROOT / path
        ok = p.exists() and p.stat().st_size > 1000
        checks.append((f"侧车-{name}", ok, f"{p.stat().st_size/1024:.0f} KB" if ok else "MISSING"))

    # 5. 现有模型
    ubj_files = list((ROOT / "models").glob("*.ubj"))
    checks.append(("现有模型", len(ubj_files) >= 3, f"{len(ubj_files)} 个 .ubj"))

    # 6. 训练脚本
    ts = ROOT / "train_v25.py"
    checks.append(("训练脚本", ts.exists(), "train_v25.py"))

    for name, ok, detail in checks:
        status = "✅" if ok else "❌"
        log(f"  {status} {name}: {detail}")

    all_ok = all(ok for _, ok, _ in checks)
    if not all_ok:
        log("❌ 前置检查未通过，请修复后重试")
        return False
    log("✅ 前置检查全部通过")
    return True

def run_icir_analysis(sample=800, start="2025-01-01"):
    """运行集合竞价因子 IC/IR 分析"""
    log("=" * 60)
    log("Step 1: 集合竞价因子 IC/IR 分析")
    log("=" * 60)

    import pandas as pd
    import numpy as np
    from call_auction_factors import ALL_FACTORS, compute_auction_factors
    from features_v2 import build_full_features_v2
    from data_fetcher import get_stock_list

    # 加载数据
    symbols = get_stock_list()["symbol"].tolist()
    kdf = pd.read_parquet(ROOT / "data" / "kline_cache" / "kline_all.parquet")

    def load_json_safe(path):
        p = ROOT / path
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            except:
                return {}
        return {}

    def bare(sym):
        s = str(sym).strip()
        if "." in s:
            s = s.split(".")[0]
        return s.zfill(6)[-6:]

    fund_flow_raw = load_json_safe("data/fund_flow_history.json")
    fund_flow = {bare(k): v for k, v in fund_flow_raw.items() if isinstance(v, dict)}
    margin_data = {bare(k): v for k, v in load_json_safe("data/margin_data.json").items() if isinstance(v, dict)}
    event_data = {bare(k): v for k, v in load_json_safe("data/event_forecast.json").items() if isinstance(v, dict)}

    # 采样
    np.random.seed(42)
    if sample and sample < len(symbols):
        sampled = sorted(np.random.choice(symbols, min(sample, len(symbols)), replace=False).tolist())
    else:
        sampled = symbols

    log(f"采样股票: {len(sampled)}")

    # 现有对比因子
    IC_COLS = ALL_FACTORS + [
        "gap_pct", "ma_cross_20_60", "ret_5d", "ret_20d",
        "vol_20d", "ma_dist_pct", "atr_pct", "turnover_ratio",
        "vol_ma_ratio", "price_vol_corr_20", "ret_range",
        "ma_cross_5_20", "eps", "roe", "profit_margin",
        "main_net_today", "main_net_5d", "main_net_10d",
        "margin_balance", "margin_buy",
        "volume_price", "momentum_accel", "trend_strength",
        "z_chip_concentration", "chip_penetration_3d",
    ]

    results = []
    t0 = time.time()
    for idx, sym in enumerate(sampled):
        try:
            code = bare(sym)
            kl = kdf[kdf["symbol"] == sym].sort_values("date").copy()
            if len(kl) < 120:
                kl = kdf[kdf["symbol"] == code].sort_values("date").copy()
            if len(kl) < 120:
                continue

            kl = kl.tail(180).reset_index(drop=True)
            kl["date"] = kl["date"].astype(str)

            feats = build_full_features_v2(
                kl,
                fund_hist=fund_flow.get(code),
                margin_data=margin_data.get(code),
                event_data=event_data.get(code),
            )
            if feats is None or len(feats) < 30:
                continue

            future_ret = feats["close"].shift(-1) / feats["close"] - 1

            for ri in range(20, len(feats) - 1):
                row = {}
                for c in IC_COLS:
                    if c in feats.columns:
                        v = feats.iloc[ri][c]
                        row[c] = float(v) if not (isinstance(v, float) and np.isnan(v)) else None
                row["_ret_fwd"] = float(future_ret.iloc[ri]) if not np.isnan(future_ret.iloc[ri]) else None
                row["_date"] = str(kl.iloc[ri]["date"])[:10]
                row["_symbol"] = code
                results.append(row)
        except Exception:
            continue

        if (idx + 1) % 100 == 0:
            log(f"  [{time.time()-t0:.0f}s] {idx+1}/{len(sampled)}, obs={len(results)}")

    log(f"总观测: {len(results)}")

    if not results:
        log("❌ 无数据，ICIR 分析跳过")
        return False

    df = pd.DataFrame(results)

    # 计算 ICIR
    ic_results = []
    for col in IC_COLS:
        if col not in df.columns:
            continue
        daily_ics = []
        for date, grp in df.groupby("_date"):
            sub = grp[[col, "_ret_fwd"]].dropna()
            if len(sub) < 20:
                continue
            ic_val = sub["_ret_fwd"].rank().corr(sub[col].rank(), method="spearman")
            if not np.isnan(ic_val):
                daily_ics.append(ic_val)

        if daily_ics:
            icir = float(np.mean(daily_ics)) / (float(np.std(daily_ics)) + 1e-10)
            ic_mean = float(np.mean(daily_ics))
            hit_rate = sum(1 for v in daily_ics if v > 0) / len(daily_ics)
            ic_results.append({
                "factor": col,
                "icir": round(icir, 4),
                "ic_mean": round(ic_mean, 4),
                "ic_std": round(float(np.std(daily_ics)), 4),
                "hit_rate": round(hit_rate, 4),
                "n_dates": len(daily_ics),
                "is_auction": col.startswith("rd_auction"),
            })

    ic_df = pd.DataFrame(ic_results).sort_values("icir", ascending=False)

    # 输出
    log(f"\n{'='*70}")
    log("IC/IR 排名 TOP 20")
    log(f"{'='*70}")
    for i, row in ic_df.head(20).iterrows():
        flag = " ★" if row["is_auction"] else ""
        log(f"  {row['factor']:35s} IC={row['ic_mean']:>.4f} ICIR={row['icir']:>.4f} HR={row['hit_rate']:>.1%}{flag}")

    # 集合竞价因子汇总
    au_ic = ic_df[ic_df["is_auction"]].copy()
    log(f"\n{'='*70}")
    log(f"集合竞价因子汇总 ({len(au_ic)} 个)")
    log(f"{'='*70}")
    log(f"  正向 ICIR: {(au_ic['icir'] > 0).sum()}  |  负向: {(au_ic['icir'] < 0).sum()}")
    log(f"  平均 |ICIR|: {au_ic['icir'].abs().mean():.4f}")
    log(f"  最大 ICIR: {au_ic['icir'].max():.4f}")
    for i, row in au_ic.sort_values("icir", ascending=False).iterrows():
        log(f"  {row['factor']:40s} IC={row['ic_mean']:>.4f} ICIR={row['icir']:>.4f}")

    # 保存
    ic_df.to_json(AUCTION_DIR / "auction_icir_analysis.json", orient="records", indent=2, force_ascii=False)
    log(f"ICIR 结果已保存至 {AUCTION_DIR / 'auction_icir_analysis.json'}")

    # 生成 ICIR 权重文件
    selected = ic_df[ic_df["is_auction"]].sort_values("icir", ascending=False)
    selected = selected[selected["icir"].abs() > 0.02]  # 过滤噪音

    weights = {}
    for _, row in selected.iterrows():
        w = abs(row["icir"])
        weights[row["factor"]] = {
            "icir": row["icir"],
            "ic_mean": row["ic_mean"],
            "weight": 0.0,  # 归一化再填
        }

    total_w = sum(abs(v["icir"]) for v in weights.values())
    if total_w > 0:
        for k in weights:
            weights[k]["weight"] = round(abs(weights[k]["icir"]) / total_w, 6)

    weight_out = {
        "version": "1.0",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_factors": len(weights),
        "factors": weights,
        "note": "集合竞价因子 ICIR 权重（本地 ICIR 分析）",
    }
    (AUCTION_DIR / "auction_icir_weights.json").write_text(
        json.dumps(weight_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"ICIR 权重已保存 ({len(weights)} 个因子)")

    return True


def retrain_model(opt_only=True):
    """重训 XGBoost 模型（含集合竞价因子）"""
    log("=" * 60)
    log("Step 2: 重训 XGBoost 模型")
    log("=" * 60)

    cmd = f"python3 -u train_v25.py --opt-only"
    if opt_only:
        log("训练模式: v25_opt only (含集合竞价因子 + 技术块)")
    else:
        log("训练模式: v25_base + v25_opt (A/B 对照)")

    ok, r = run(cmd)
    if not ok:
        log("❌ 训练失败")
        return False

    # 解析训练输出
    for line in r.stdout.split("\n"):
        if "V25_opt" in line or "AUC" in line or "边际增益" in line or "总样本" in line:
            log(f"  {line.strip()}")

    # 备份元数据
    meta_path = MODEL_DIR / "v25_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        out_meta = AUCTION_DIR / "training_meta.json"
        out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"训练元数据已保存至 {out_meta}")

    log("✅ 模型训练完成")
    return True


def run_backtest(start="2026-04-01", end=None):
    """运行可交易回测对比"""
    log("=" * 60)
    log("Step 3: 回测对比（新模型 vs 旧基线）")
    log("=" * 60)

    if end is None:
        import pandas as pd
        kdf = pd.read_parquet(ROOT / "data" / "kline_cache" / "kline_all.parquet")
        end = str(kdf["date"].astype(str).str[:10].max())

    # 备份旧模型
    backup_dir = MODEL_DIR / "backup_before_auction"
    if not backup_dir.exists():
        backup_dir.mkdir(parents=True)
        for f in MODEL_DIR.glob("v25_*.ubj"):
            shutil.copy2(f, backup_dir / f.name)
        if (MODEL_DIR / "v25_meta.json").exists():
            shutil.copy2(MODEL_DIR / "v25_meta.json", backup_dir / "v25_meta.json")
        log(f"旧模型已备份至 {backup_dir}")

    # 运行回测
    cmd = f"python3 -u backtest_v3_tradable_gated.py --start {start} --end {end}"
    ok, r = run(cmd)

    if ok:
        log("回测输出片段:")
        for line in r.stdout.split("\n"):
            if any(kw in line for kw in ["A0", "A1_cur", "A1_ladder", "胜率", "命中", "年化", "总收益"]):
                log(f"  {line.strip()}")

    # 运行 OOS 验证
    cmd = "python3 scripts/run_oos_tradable_top2.py"
    oos_ok, oos_r = run(cmd, timeout_min=30)
    if oos_ok:
        log("OOS 验证输出:")
        for line in oos_r.stdout.split("\n"):
            if any(kw in line for kw in ["PASS", "FAIL", "fill", "hit", "gate"]):
                log(f"  {line.strip()}")


    log("✅ 回测完成")
    return ok


def generate_report():
    """生成训练结果报告"""
    log("=" * 60)
    log("Step 4: 生成训练报告")
    log("=" * 60)

    report = {
        "title": "集合竞价因子深度集成 — 训练报告",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "steps": {},
    }

    icir_path = AUCTION_DIR / "auction_icir_analysis.json"
    if icir_path.exists():
        icir_data = json.loads(icir_path.read_text(encoding="utf-8"))
        auction_ics = [r for r in icir_data if r.get("is_auction")]
        report["steps"]["icir_analysis"] = {
            "n_auction_factors": len(auction_ics),
            "top_auction_factors": [r["factor"] for r in sorted(auction_ics, key=lambda x: -abs(x["icir"]))[:10]],
            "avg_abs_icir": round(sum(abs(r["icir"]) for r in auction_ics) / len(auction_ics), 4) if auction_ics else 0,
            "positive_icir": sum(1 for r in auction_ics if r["icir"] > 0),
            "n_dates": max(r.get("n_dates", 0) for r in auction_ics) if auction_ics else 0,
        }

    meta_path = AUCTION_DIR / "training_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ab = meta.get("ab_test", {})
        report["steps"]["training"] = {
            "v25_base_auc": ab.get("v25_base_auc"),
            "v25_opt_auc": ab.get("v25_opt_auc"),
            "tech_block_gain": ab.get("tech_block_marginal_gain"),
            "n_samples": meta.get("training", {}).get("n_samples"),
            "n_features": meta.get("features", {}).get("base_count", 0),
            "extra_factors": meta.get("features", {}).get("extra_rd_factors", []),
        }

    (AUCTION_DIR / "training_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"报告已保存至 {AUCTION_DIR / 'training_report.json'}")
    log(f"\n{'='*60}")
    log("训练流程完成！")
    log(f"{'='*60}")
    log(f"结果目录: {AUCTION_DIR}")
    log("文件清单:")
    for f in sorted(AUCTION_DIR.iterdir()):
        log(f"  {f.name} ({f.stat().st_size/1024:.1f} KB)")

    return True


def main():
    import argparse
    ap = argparse.ArgumentParser(description="集合竞价因子全流程训练")
    ap.add_argument("--icir-only", action="store_true", help="只运行 ICIR 分析")
    ap.add_argument("--train-only", action="store_true", help="只运行模型训练")
    ap.add_argument("--backtest-only", action="store_true", help="只运行回测")
    ap.add_argument("--sample", type=int, default=0, help="ICIR 采样数 (0=全市场)")
    ap.add_argument("--skip-check", action="store_true", help="跳过前置检查")
    ap.add_argument("--no-retrain", action="store_true", help="跳过重训（只跑 ICIR）")
    args = ap.parse_args()

    t_start = time.time()

    if not args.skip_check and not (args.backtest_only or args.train_only):
        if not check_prerequisites():
            sys.exit(1)

    if args.icir_only:
        ret = run_icir_analysis(sample=args.sample or 800)
        if ret:
            generate_report()
        log(f"总耗时: {time.time()-t_start:.0f}s")
        sys.exit(0 if ret else 1)

    if args.backtest_only:
        ret = run_backtest()
        log(f"总耗时: {time.time()-t_start:.0f}s")
        sys.exit(0 if ret else 1)

    if args.train_only:
        ret = retrain_model()
        if ret:
            ret = run_backtest()
        generate_report()
        log(f"总耗时: {time.time()-t_start:.0f}s")
        sys.exit(0 if ret else 1)

    # 完整流程
    if not check_prerequisites():
        sys.exit(1)

    ok = run_icir_analysis(sample=args.sample or 800)
    if ok and not args.no_retrain:
        ok = retrain_model()
    if ok and not args.no_retrain:
        ok = run_backtest()
    generate_report()

    log(f"总耗时: {time.time()-t_start:.0f}s")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()