#!/usr/bin/env python3
"""Deploy mixed maker/taker execution, retrain, restart, verify vs taker baseline."""
import paramiko, os, time, warnings
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
for f in ["config.py", "grid_backtest.py", "backtest.py", "paper_trader.py", "sg_pipeline.py"]:
    sftp.put(os.path.join(LOCAL, "crypto", f).replace("\\", "/"),
             f"/home/ubuntu/alphapilot/crypto/{f}")
sftp.close()
log("uploaded 5 files")

# Stop trader
run("sudo systemctl stop alphapilot-crypto-paper 2>/dev/null || true")

# Retrain + backtest with maker execution
run("cd /home/ubuntu/alphapilot && python3 crypto/sg_pipeline.py", timeout=900)

# Restart trader
run("sudo systemctl restart alphapilot-crypto-paper")
time.sleep(3)
run("sudo systemctl is-active alphapilot-crypto-paper")

# Verify config
run("grep -nE 'MAKER_FEE|TAKER_FEE' /home/ubuntu/alphapilot/crypto/config.py")

conn.close()
log("DONE!")
