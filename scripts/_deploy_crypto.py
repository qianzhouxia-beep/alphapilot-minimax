#!/usr/bin/env python3
"""Deploy crypto v2 to Singapore server using paramiko (pure Python SSH)."""
import paramiko, os, sys, time, warnings
warnings.filterwarnings("ignore")

HOST = "43.156.119.47"
USER = "ubuntu"
PASSWORD = "Sef-9i7k]1zjicK6Nv"
ROOT = "/home/ubuntu/alphapilot"
LOCAL = r"C:\Users\elvisq\Projects\alphapilot"

SERVICE_NAME = "alphapilot-crypto-paper"
SERVICE_FILE = os.path.join(LOCAL, "scripts", f"{SERVICE_NAME}.service").replace("\\", "/")

CRYPTO_FILES = [
    "__init__.py", "config.py", "data.py", "features.py", "icir.py",
    "train.py", "backtest.py", "simulate.py", "optimize.py",
    "grid_backtest.py", "sg_pipeline.py", "paper_trader.py",
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ssh():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    return c


def run(conn, cmd, timeout=60):
    log(f"$ {cmd[:120]}")
    _, stdout, stderr = conn.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if out:
        for line in out.split("\n")[-10:]:
            print(f"  {line}")
    if exit_code != 0 and err:
        print(f"  (stderr) {err[-200:]}")
    return exit_code, out


def sftp_put(conn, local_path, remote_path):
    with conn.open_sftp() as s:
        s.put(local_path, remote_path)
    print(f"  -> {remote_path}")


log("=" * 50)
log("Crypto v2 Deploy to Singapore")
log("=" * 50)

conn = ssh()
log(f"Connected to {HOST}")

# Step 1: Create directories
log("\n--- Step 1: Create directories ---")
run(conn, f"mkdir -p {ROOT}/crypto {ROOT}/data/crypto {ROOT}/output/crypto")

# Step 2: Upload crypto module files
log("\n--- Step 2: Upload crypto module ---")
for f in CRYPTO_FILES:
    local = os.path.join(LOCAL, "crypto", f).replace("\\", "/")
    remote = f"{ROOT}/crypto/{f}"
    sftp_put(conn, local, remote)

# Step 3: Install Python deps
log("\n--- Step 3: Install Python deps ---")
run(conn, (
    "cd /home/ubuntu/alphapilot && "
    "pip3 install ccxt xgboost pandas numpy scipy scikit-learn --break-system-packages 2>&1 | tail -5"
), timeout=180)

# Step 4: Run full pipeline
log("\n--- Step 4: Run initial pipeline ---")
run(conn, "cd /home/ubuntu/alphapilot && python3 crypto/sg_pipeline.py", timeout=600)

# Step 5: Install daily cron
log("\n--- Step 5: Install daily retrain cron ---")
CRON_SCRIPT = """#!/bin/bash
cd /home/ubuntu/alphapilot
LOGFILE="/home/ubuntu/alphapilot/output/crypto/cron_train.log"
echo "===== $(date) =====" >> $LOGFILE
python3 crypto/sg_pipeline.py >> $LOGFILE 2>&1
echo "Done: $(date)" >> $LOGFILE
"""
run(conn, f"cat > {ROOT}/crypto_daily_train.sh << 'CRONEOF'\n{CRON_SCRIPT}\nCRONEOF")
run(conn, f"chmod +x {ROOT}/crypto_daily_train.sh")
run(conn, "(crontab -l 2>/dev/null | grep -v crypto_daily; echo '0 22 * * * /home/ubuntu/alphapilot/crypto_daily_train.sh') | crontab -")
run(conn, "crontab -l")

# Step 6: Install 24/7 systemd paper trader service
log("\n--- Step 6: Install 24/7 paper trader systemd service ---")

# Stop existing service if running
run(conn, f"sudo systemctl stop {SERVICE_NAME} 2>/dev/null || true")

# Upload service file
sftp_put(conn, SERVICE_FILE, f"/tmp/{SERVICE_NAME}.service")

# Install
run(conn, f"sudo mv /tmp/{SERVICE_NAME}.service /etc/systemd/system/{SERVICE_NAME}.service")
run(conn, "sudo systemctl daemon-reload")
run(conn, f"sudo systemctl enable {SERVICE_NAME}")
run(conn, f"sudo systemctl restart {SERVICE_NAME}")
time.sleep(2)
run(conn, f"sudo systemctl status {SERVICE_NAME} --no-pager | head -15")
log("Paper trader service installed and started")

# Step 7: Set up SSH key for future passwordless access
log("\n--- Step 7: Generate SSH key on server ---")
run(conn, "mkdir -p ~/.ssh && chmod 700 ~/.ssh")
k = run(conn, "ls ~/.ssh/id_alphapilot 2>/dev/null || echo 'not_found'")
if "not_found" in k[1]:
    run(conn, "ssh-keygen -t ed25519 -f ~/.ssh/id_alphapilot -N '' -q")
    run(conn, "cat ~/.ssh/id_alphapilot.pub >> ~/.ssh/authorized_keys")
    run(conn, "chmod 600 ~/.ssh/authorized_keys")
    log("SSH key generated")

# Download private key for future use
log("\n--- Step 8: Download SSH private key ---")
local_key = os.path.join(LOCAL, "sg_key").replace("\\", "/")
with conn.open_sftp() as s:
    s.get("/home/ubuntu/.ssh/id_alphapilot", local_key)
log(f"Key saved: {local_key}")

# Step 9: Fetch report & verify service
log("\n--- Step 9: Verification ---")
run(conn, "cat /home/ubuntu/alphapilot/output/crypto/sg_server_report.json 2>/dev/null || echo '(pipeline still running)'")
run(conn, f"sudo systemctl is-active {SERVICE_NAME}")
run(conn, f"journalctl -u {SERVICE_NAME} -n 10 --no-pager 2>/dev/null")

conn.close()

log("\n" + "=" * 50)
log("DEPLOY COMPLETE!")
log(f"  Server:    {USER}@{HOST}")
log(f"  Config:    BTC/ETH/SOL/XRP/BNB | 2h model | 2h entry | 10% risk")
log(f"  Service:   {SERVICE_NAME} (24/7 paper trader)")
log(f"  Cron:      SGT 06:00 daily retrain")
log(f"  Key:       ssh -i sg_key {USER}@{HOST}")
log("=" * 50)
