#!/usr/bin/env python3
"""Deploy OR/POC factors to Singapore server."""
import paramiko, time, json

HOST = "43.156.119.47"
USER = "ubuntu"
PASSWORD = "Sef-9i7k]1zjicK6Nv"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=30)

def run(cmd, timeout=120):
    _, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return out, err, exit_code

# 1. Stop paper trader
print("--- Stopping paper trader ---")
run("sudo systemctl stop alphapilot-crypto-paper 2>/dev/null || true")
time.sleep(1)

# 2. Upload features.py
print("--- Uploading features.py ---")
with c.open_sftp() as s:
    s.put("crypto/features.py", "/home/ubuntu/alphapilot/crypto/features.py")
print("  Uploaded features.py")

# 3. Run full pipeline
print("--- Running sg_pipeline (retrain with new factors) ---")
out, err, ec = run("cd /home/ubuntu/alphapilot && python3 crypto/sg_pipeline.py", timeout=600)
for line in out.split("\n")[-35:]:
    print(f"  {line}")
if err:
    print(f"  STDERR: {err[:800]}")

# 4. Restart paper trader
print("--- Restarting paper trader ---")
run("sudo systemctl restart alphapilot-crypto-paper")
time.sleep(3)
out, _, _ = run("sudo systemctl is-active alphapilot-crypto-paper")
print(f"  Service: {out}")
out, _, _ = run("tail -8 /home/ubuntu/alphapilot/output/crypto/paper_trader.log 2>/dev/null")
print("  Log:")
for l in out.split("\n"):
    print(f"    {l}")

# 5. Verify report
print("--- Verify report ---")
out, _, _ = run("cat /home/ubuntu/alphapilot/output/crypto/sg_server_report.json")
try:
    r = json.loads(out)
    print(f'  AUC: {r.get("long_auc", "N/A")}')
    cfg = r.get("config", {})
    print(f'  n_factors: {cfg.get("n_factors", "N/A")}')
    g = r.get("grid_backtest", {})
    print(f'  Grid return: {g.get("total_return_pct", "N/A")}%')
    print(f'  Grid max_dd: {g.get("max_dd_pct", "N/A")}%')
    print(f'  Grid win_rate: {g.get("win_rate_pct", "N/A")}%')
except Exception as e:
    print(f"  Error parsing report: {e}")

# 6. Show ICIR top factors to confirm new ones selected
print("--- ICIR top factors ---")
out, _, _ = run("cat /home/ubuntu/alphapilot/data/crypto/icir_weights.json")
try:
    icir = json.loads(out)
    ranked = sorted(icir.get("summary", {}).items(), key=lambda x: -x[1].get("abs_icir", 0))
    new_factors = [f for f, _ in ranked if f.startswith("or_") or f.startswith(("poc_", "vwap_"))]
    print(f"  New OR/POC factors in ranking: {len(new_factors)}")
    for f in new_factors[:8]:
        print(f"    {f}")
except Exception as e:
    print(f"  Error parsing ICIR: {e}")

c.close()
print()
print("Deploy complete!")
