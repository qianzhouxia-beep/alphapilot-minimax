#!/usr/bin/env python3
"""Deploy per-direction thresholds (long 0.45 / short 0.50) + retrain + verify."""
import paramiko, os, sys, time, warnings
warnings.filterwarnings("ignore")

HOST = "43.156.119.47"
USER = "ubuntu"
PASSWORD = "Sef-9i7k]1zjicK6Nv"
LOCAL = r"C:\Users\elvisq\Projects\alphapilot"

def log(msg): print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

conn = paramiko.SSHClient()
conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
conn.connect(HOST, username=USER, password=PASSWORD, timeout=30)

def run(cmd, timeout=60):
    log(f"$ {cmd[:110]}")
    _, stdout, stderr = conn.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if out:
        for line in out.split("\n")[-35:]:
            print(f"  {line}")
    if exit_code != 0 and err:
        print(f"  (stderr) {err[-400:]}")
    return exit_code, out

# Upload changed files
sftp = conn.open_sftp()
for f in ["config.py", "paper_trader.py", "simulate.py", "grid_backtest.py", "backtest.py", "sg_pipeline.py"]:
    sftp.put(os.path.join(LOCAL, "crypto", f).replace("\\", "/"),
             f"/home/ubuntu/alphapilot/crypto/{f}")
sftp.close()
log("uploaded 6 files")

# Stop trader
run("sudo systemctl stop alphapilot-crypto-paper 2>/dev/null || true")

# Retrain + verify
run("cd /home/ubuntu/alphapilot && python3 crypto/sg_pipeline.py", timeout=900)

# Restart trader
run("sudo systemctl restart alphapilot-crypto-paper")
time.sleep(3)
run("sudo systemctl is-active alphapilot-crypto-paper")

# Verify config + thresholds
run("grep -n 'min_signal_score' /home/ubuntu/alphapilot/crypto/config.py")
run("python3 -c \"import json; d=json.load(open('/home/ubuntu/alphapilot/output/crypto/sg_server_report.json')); print('config:', d.get('config',{})); print('long_auc:', round(d['long_auc'],4), 'short_auc:', round(d['short_auc'],4)); g=d.get('grid_backtest',{}); print('grid:', g.get('n_trades'), 'trades, win', g.get('win_rate_pct'), '%, ret', g.get('total_return_pct'), '%, dd', g.get('max_dd_pct'), '%')\"")

conn.close()
log("DONE!")
