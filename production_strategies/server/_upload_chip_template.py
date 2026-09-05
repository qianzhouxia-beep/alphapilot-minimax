# -*- coding: utf-8 -*-
"""合并当日筹码批次 + 服务器旧数据兜底，上传上海服务器双路径。

模板（2026-08-25 铁律）：开头内嵌 check_chip_batches 校验，
returncode != 0 即 exit(1) —— 物理上禁止"侥幸上传半截数据"（08-24 事故教训）。

用法：
    python _upload_chip_template.py <YYYY-MM-DD | YYYYMMDD> [--dir <批次目录>]

- 不传 --dir 时，批次目录 = 本脚本所在目录（即 _chip_batch_*_{suffix}.json 所在处）。
- DATE 支持 2026-08-25 或 20260825，脚本自动识别。
"""
import paramiko, json, io, glob, time, sys, os, subprocess
from collections import Counter

CHECK_SCRIPT = r"C:\Users\elvisq\Projects\alphapilot\production_strategies\server\check_chip_batches.py"
HOST = "150.158.100.236"
KEY_CANDIDATES = [
    r"C:\Users\elvisq\Downloads\AlphaPiolot.pem",  # 优先（2026-08-24 恢复存在）
    r"C:\Users\elvisq\key.pem",                     # fallback
]
REMOTE_PATH = "/home/ubuntu/alphapilot/data/chip_data_all.json"
REMOTE_PATH2 = "/home/ubuntu/alphapilot/chip_data_all.json"
LOCAL_NEW = r"C:\Users\elvisq\Projects\alphapilot\chip_data_all_new.json"


def _date_suffix(date: str) -> str:
    s = date.replace("-", "")
    return s[-4:] if s.startswith("20") else s  # 20260825 -> 0825


def _connect():
    last_err = None
    for kp in KEY_CANDIDATES:
        if not os.path.exists(kp):
            continue
        try:
            k = paramiko.RSAKey.from_private_key_file(kp)
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(HOST, username="ubuntu", pkey=k, timeout=20)
            return ssh
        except Exception as ex:  # noqa: BLE001
            last_err = ex
    raise RuntimeError(f"无法用任一密钥连接服务器: {last_err}")


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python _upload_chip_template.py <YYYY-MM-DD|YYYYMMDD> [--dir <批次目录>]")
        return 2

    date = sys.argv[1]
    batch_dir = os.path.dirname(os.path.abspath(__file__))
    if "--dir" in sys.argv:
        batch_dir = sys.argv[sys.argv.index("--dir") + 1]
    suffix = _date_suffix(date)
    ts = time.strftime("%Y%m%d_%H%M")

    # ── 上传前批次完整性校验（2026-08-25 强制，双保险）──
    r = subprocess.run(
        [sys.executable, CHECK_SCRIPT, "--date", date, "--dir", batch_dir],
        capture_output=True, text=True,
    )
    print(r.stdout)
    if r.returncode != 0:
        print("[UPLOAD BLOCKED] 批次校验不通过，禁止上传（08-24 事故教训）。请先补拉缺失批次重跑校验。")
        return 1

    # 1. 合并本地当日批次
    merged = {}
    for fn in sorted(glob.glob(os.path.join(batch_dir, f"_chip_batch_*_{suffix}.json"))):
        with open(fn, "r", encoding="utf-8") as f:
            d = json.load(f)
        data = d.get("data", d)
        for code, v in data.items():
            merged[code[-6:]] = v
    print(f"本地批次合并: {len(merged)} 只")
    c0 = Counter(str(v.get("date"))[:10] for v in merged.values())
    print(f"本地 date 分布: {dict(c0)}")

    # 2. 连服务器下载现有数据
    ssh = _connect()
    sftp = ssh.open_sftp()
    with sftp.open(REMOTE_PATH, "r") as f:
        server_raw = json.load(f)
    server_data = server_raw.get("data", server_raw)
    print(f"服务器现有 data/: {len(server_data)} 只")
    print(f"服务器 data/ date 分布: {dict(Counter(str(v.get('date'))[:10] for v in server_data.values()))}")

    # 3. 合并：本地新数据覆盖，缺失保留旧数据
    new_data = {}
    for key, v in server_data.items():
        kk = key[-6:] if len(key) >= 6 else key
        new_data[kk] = v
    for code, v in merged.items():
        new_data[code[-6:]] = v

    merged_all = {"ok": True, "data": new_data}

    # ── 2026-08-29 上传前消费者契约校验（08-24 事故教训）──
    # 上传模板写出 {ok,data} 包装；train_v25/vm25_scorer 直接取顶层读不到 →
    # 必须模拟消费者路径确认能解出足够筹码，否则禁止上传。
    consumer = merged_all.get("data", merged_all) if isinstance(merged_all, dict) else merged_all
    consumer = {k: v for k, v in consumer.items() if isinstance(v, dict)} if isinstance(consumer, dict) else {}
    if len(consumer) < 4000:
        print(
            f"[UPLOAD BLOCKED] 消费者契约校验失败：train/vm25 直接取顶层仅解出 "
            f"{len(consumer)} 只（<4000）。合并后结构会再次导致训练/打分筹码落空，禁止上传。",
            flush=True,
        )
        return 1
    print(f"[UPLOAD CHECK] 消费者契约通过：取顶层可解 {len(consumer)} 只（train/vm25 可读）")

    out_json = json.dumps(merged_all, ensure_ascii=False).encode("utf-8")
    print(f"合并后: {len(new_data)} 只")
    print(f"合并后 date 分布: {dict(Counter(str(v.get('date'))[:10] for v in new_data.values()))}")

    # 4. 本地保存
    with open(LOCAL_NEW, "w", encoding="utf-8") as f:
        json.dump(merged_all, f, ensure_ascii=False)
    print(f"本地保存: {LOCAL_NEW}")

    # 5. 服务器备份 + 上传双路径
    for p in [REMOTE_PATH, REMOTE_PATH2]:
        bak = f"{p}.bak_merge_{date}_{ts}"
        ssh.exec_command(f"cp {p} {bak}")
        time.sleep(1)
        print(f"备份: {bak}")
    buf = io.BytesIO(out_json)
    sftp.putfo(buf, REMOTE_PATH)
    buf2 = io.BytesIO(out_json)
    sftp.putfo(buf2, REMOTE_PATH2)
    print("上传完成: data/ 与 根目录")

    # 6. 验证
    ok = True
    for p in [REMOTE_PATH, REMOTE_PATH2]:
        cmd = (f"python3 -c \"import json;d=json.load(open('{p}'));"
               f"data=d.get('data',d);from collections import Counter;"
               f"c=Counter(str(v.get('date'))[:10] for v in data.values());"
               f"print(len(data), dict(c))\"")
        _, o, e = ssh.exec_command(cmd, timeout=30)
        out = o.read().decode().strip()
        err = e.read().decode().strip()
        print(f"[{p}] {out} {err[:200] if err else ''}")
        compact = date.replace("-", "")
        expected = f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
        if expected not in out:
            ok = False
    ssh.close()
    if not ok:
        print("[WARN] 服务器 date 分布未全部命中当日，请复查 data_readiness_gate。")
        return 1
    print("[OK] 上传成功且服务器当日筹码已落地。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
