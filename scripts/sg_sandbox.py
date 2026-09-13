#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新加坡算力沙箱入口 —— 在 SG 用「与生产同版本依赖」跑重算力任务。

规则见 `.cursor/rules/compute-host.mdc`：
  · 上海（150.158.100.236）= 生产机（3.6GB），**不跑**回测/训练/因子挖掘
  · 新加坡（43.156.119.47）= 沙箱（15.6GB），重算力一律在此
  · 必须用 pylibs 里的锁定版本，否则结果与生产不可比

用法（在仓库根目录）:
  python3 scripts/sg_sandbox.py --sync                       # 同步代码 → 沙箱
  python3 scripts/sg_sandbox.py --sync-data                  # 从上海拉数据 → 沙箱
  python3 scripts/sg_sandbox.py --sync --run "rd_workshop/walkforward_oos.py --folds 6 --test-days 21 --run-id baseline"
  python3 scripts/sg_sandbox.py --status                     # 看沙箱状态
  python3 scripts/sg_sandbox.py --fetch rd_workshop/walkforward_runs/<id>/report.json ./_sg_out/
"""
from __future__ import annotations

import argparse
import hashlib
import io
import pathlib
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bt_research"))
import sg_util  # noqa: E402

SG_HOST = sg_util.HOST
DEST = "/home/ubuntu/bt_sandbox/alphapilot"
PYLIBS = "/home/ubuntu/bt_sandbox/pylibs"
SH = "ubuntu@150.158.100.236"
SH_ROOT = "/home/ubuntu/alphapilot"
SG_KEY = "/home/ubuntu/.ssh/alphapilot.pem"

# 复现生产口径所依赖的根级模块（md5 漂移检查用）
CRITICAL_MODULES = [
    "train_v25.py",
    "features_v2.py",
    "auto_factor_engine.py",
    "data_fetcher.py",
    "vm25_scorer.py",
    "recommend.py",
]

DATA_FILES = [
    "data/kline_cache/kline_all.parquet",
    "data/fund_flow_history.json",
    "data/margin_data.json",
    "data/event_forecast.json",
    "data/fundamental_data.json",
    "data/lhb_history.json",
    "data/chip_data_all.json",
    "fundamental_data.json",
    "chip_data_all.json",
]
MODEL_FILES = [
    "models/v25_opt_ensemble_1.ubj",
    "models/v25_opt_ensemble_2.ubj",
    "models/v25_opt_ensemble_3.ubj",
    "models/v25_meta.json",
    "models/best_tech_params.json",
]


def sync_code(sg) -> None:
    """代码同步（两种来源，各司其职）：

      · 根级 `*.py` ← 从**生产服务器** rsync（沙箱须复现生产口径；本地仓库可能与生产漂移，
        2026-09-13 实测 `features_v2.py` 本地 `eaeb2915…` ≠ 生产 `67f6b0ff…`）
      · `rd_workshop/*.py` ← 从**本地仓库**推（研究代码以仓库为准）
    """
    rs = f"ssh -i {SG_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=20 -o BatchMode=yes"
    o, e, c = sg_util.run(
        sg,
        f"rsync -az --timeout=120 -e \"{rs}\" --include='/*.py' --exclude='*' "
        f"{SH}:{SH_ROOT}/ {DEST}/ ; echo root_rc=$?",
        timeout=600,
    )
    print(f"[sync] 生产根级 *.py ← 服务器 ({o.strip()}) {e.strip()[-200:]}")

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for p in sorted((ROOT / "rd_workshop").glob("*.py")):
            tf.add(p, arcname=f"rd_workshop/{p.name}")
    n = len(tarfile.open(fileobj=io.BytesIO(buf.getvalue()), mode="r:gz").getnames())
    buf.seek(0)
    sftp = sg.open_sftp()
    try:
        sftp.putfo(buf, "/tmp/sg_rw.tgz")
    finally:
        sftp.close()
    o, e, c = sg_util.run(sg, f"tar xzf /tmp/sg_rw.tgz -C {DEST} && echo ok", timeout=120)
    print(f"[sync] rd_workshop {n} 个 .py ← 本地仓库 ({o.strip()})")


def _md5_local(p: pathlib.Path) -> str:
    """内容 md5（忽略 CRLF/LF），避免「仅换行差异」被当成代码漂移。"""
    return hashlib.md5(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def drift_check(sg) -> None:
    """比对「本地仓库 vs 生产服务器」关键模块内容 md5（换行无关）。

    2026-09-13：`features_v2.py` 曾被 raw md5 误报漂移，实际仅 CRLF vs LF。
    """
    rs = f"ssh -i {SG_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=20 -o BatchMode=yes"
    remote_py = (
        "import hashlib, pathlib, os, sys\n"
        "root = '/home/ubuntu/alphapilot'\n"
        "def nmd5(p):\n"
        "    b = pathlib.Path(p).read_bytes().replace(b'\\r\\n', b'\\n').replace(b'\\r', b'\\n')\n"
        "    return hashlib.md5(b).hexdigest()\n"
        "for n in sys.argv[1:]:\n"
        "    p = os.path.join(root, n)\n"
        "    if os.path.isfile(p):\n"
        "        print(nmd5(p), n)\n"
    )
    sftp = sg.open_sftp()
    try:
        with sftp.file("/tmp/_nmd5_prod.py", "w") as fh:
            fh.write(remote_py)
    finally:
        sftp.close()
    names = " ".join(CRITICAL_MODULES)
    o, e, c = sg_util.run(
        sg,
        f"scp -q -i {SG_KEY} -o StrictHostKeyChecking=no -o BatchMode=yes "
        f"/tmp/_nmd5_prod.py {SH}:/tmp/_nmd5_prod.py && "
        f"{rs} {SH} 'python3 /tmp/_nmd5_prod.py {names}'",
        timeout=120,
    )
    remote = {}
    for line in o.splitlines():
        parts = line.split()
        if len(parts) == 2:
            remote[parts[1]] = parts[0]
    drift = []
    print("[drift] 本地仓库 vs 生产服务器（内容 md5，忽略 CRLF/LF）")
    for f in CRITICAL_MODULES:
        lp = ROOT / f
        if not lp.exists():
            print(f"  --   {f}  （本地缺）")
            continue
        lm = _md5_local(lp)
        rm = remote.get(f)
        if rm is None:
            print(f"  ?    {f}  （服务器缺）")
        elif lm == rm:
            print(f"  OK   {f}  {lm[:12]}")
        else:
            drift.append(f)
            print(f"  ⚠DRIFT {f}  本地 {lm[:12]} ≠ 生产 {rm[:12]}")
    if drift:
        print(f"\n⚠️ {len(drift)} 个关键模块「仓库≠生产」：{', '.join(drift)}")
        print("   → 沙箱复现生产请用服务器版（--sync 已按此拉取）；并尽快核对是否应把生产版回写仓库。")
    else:
        print("   ✅ 无内容漂移（换行差异已忽略）")
    if c != 0 and not remote:
        print(f"   remote rc={c} err={e[-200:]}")


def sync_data(sg) -> None:
    """从上海单向下拉数据/模型到沙箱（绝不反向写）。"""
    files = " ".join(f"{SH_ROOT}/{f}" for f in DATA_FILES + MODEL_FILES)
    cmd = (
        f"mkdir -p {DEST}/data/kline_cache {DEST}/models; "
        f"CD='-o StrictHostKeyChecking=no -o ConnectTimeout=20 -o BatchMode=yes'; "
        f"cd {SH_ROOT} 2>/dev/null; "
        f"rsync -az --timeout=120 -e \"ssh -i {SG_KEY} $CD\" "
        f"--files-from=- {SH}:{SH_ROOT}/ {DEST}/ <<'EOF'\n"
        + "\n".join(DATA_FILES + MODEL_FILES)
        + "\nEOF\necho data_ok"
    )
    o, e, c = sg_util.run(sg, cmd, timeout=900)
    print(f"[data] rc={c} {o.strip()[-200:]} {e.strip()[-200:]}")


def run_script(sg, script: str) -> int:
    cmd = (
        f"cd {DEST} && ALPHAPILOT_ROOT={DEST} PYTHONPATH={PYLIBS} "
        f"nice -n 10 python3 -u {script}"
    )
    print(f"[run] {cmd}", flush=True)
    _, stdout, stderr = sg.exec_command(cmd, timeout=14400)
    for line in iter(stdout.readline, ""):
        if not line:
            break
        print(line.rstrip(), flush=True)
    rc = stdout.channel.recv_exit_status()
    err = stderr.read().decode("utf-8", "replace")
    if err.strip():
        print("[stderr]", err[-2000:])
    print(f"[run] exit={rc}")
    return rc


def status(sg) -> None:
    o, _, _ = sg_util.run(
        sg,
        f"echo '--- sandbox ---'; du -sh /home/ubuntu/bt_sandbox 2>/dev/null; "
        f"ls {DEST}/data/kline_cache/ 2>/dev/null; ls {DEST}/models/ 2>/dev/null; "
        f"echo '--- mem ---'; free -m | head -2; echo '--- load ---'; uptime",
        timeout=90,
    )
    print(o)


def fetch(sg, remote: str, local: str) -> None:
    d = pathlib.Path(local)
    d.mkdir(parents=True, exist_ok=True)
    sftp = sg.open_sftp()
    try:
        sftp.get(remote, str(d / pathlib.Path(remote).name))
    finally:
        sftp.close()
    print(f"[fetch] {remote} → {d / pathlib.Path(remote).name}")


def main() -> int:
    ap = argparse.ArgumentParser(description="新加坡算力沙箱")
    ap.add_argument("--sync", action="store_true", help="同步代码 → SG 沙箱（根模块←生产 / rd_workshop←仓库）")
    ap.add_argument("--sync-data", action="store_true", help="从上海拉数据/模型 → SG 沙箱")
    ap.add_argument("--drift", action="store_true", help="比对本地仓库 vs 生产服务器关键模块 md5")
    ap.add_argument("--run", default="", help="在沙箱里跑的脚本+参数（相对沙箱根）")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--fetch", nargs=2, metavar=("REMOTE", "LOCAL"), default=None)
    args = ap.parse_args()

    sg = sg_util.client()
    try:
        if args.status:
            status(sg)
        if args.drift:
            drift_check(sg)
        if args.sync:
            sync_code(sg)
        if args.sync_data:
            sync_data(sg)
        if args.fetch:
            fetch(sg, args.fetch[0], args.fetch[1])
        if args.run:
            return run_script(sg, args.run)
        if not (args.status or args.sync or args.sync_data or args.fetch or args.drift):
            ap.print_help()
    finally:
        sg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
