#!/usr/bin/env python3
"""Check Singapore server paper trader status."""
import paramiko, json

HOST = "43.156.119.47"
USER = "ubuntu"
PASSWORD = "Sef-9i7k]1zjicK6Nv"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=30)

def run(cmd):
    _, stdout, stderr = c.exec_command(cmd, timeout=30)
    exit_code = stdout.channel.recv_exit_status()
    return stdout.read().decode().strip(), stderr.read().decode().strip(), exit_code

# 1. Service status
print("=" * 55)
print("SERVICE STATUS")
print("=" * 55)
out, _, _ = run("sudo systemctl is-active alphapilot-crypto-paper")
print(f"  alphapilot-crypto-paper: {out}")
out, _, _ = run("journalctl -u alphapilot-crypto-paper -n 5 --no-pager")
print(f"  Recent journal:")
for line in out.split("\n")[-5:]:
    print(f"    {line.strip()}")

# 2. Paper trader output log
print()
print("=" * 55)
print("PAPER TRADER LOG (last 20 lines)")
print("=" * 55)
out, _, _ = run("tail -20 /home/ubuntu/alphapilot/output/crypto/paper_trader.log 2>/dev/null")
print(out[-2000:] if len(out) > 2000 else out)

# 3. Paper status via Python
print()
print("=" * 55)
print("PAPER STATUS")
print("=" * 55)
_, stdout, _ = c.exec_command(
    'cd /home/ubuntu/alphapilot && python3 -c "from crypto.paper_trader import print_status; print_status()"',
    timeout=30
)
out = stdout.read().decode().strip()
print(out)

# 4. Equity curve
print()
print("=" * 55)
print("EQUITY CURVE (last 5 points)")
print("=" * 55)
out, _, _ = run("tail -5 /home/ubuntu/alphapilot/output/crypto/paper_equity.jsonl 2>/dev/null")
for line in out.split("\n"):
    if line.strip():
        try:
            d = json.loads(line)
            print(f"  {d['ts'][:19]}  equity=${d['equity']:.2f}  capital=${d['capital']:.2f}  trades={d['trades']}  pos={d['positions']}")
        except:
            pass

# 5. Server report
print()
print("=" * 55)
print("LATEST TRAINING REPORT")
print("=" * 55)
out, _, _ = run("cat /home/ubuntu/alphapilot/output/crypto/sg_server_report.json 2>/dev/null")
if out:
    try:
        r = json.loads(out)
        c = r.get("config", {})
        print(f"  Long AUC:       {r.get('long_auc', 'N/A')}")
        print(f"  Training TF:    {c.get('training_tf', 'N/A')}")
        print(f"  Entry TF:       {c.get('entry_tf', 'N/A')}")
        print(f"  Forward:        {c.get('forward', 'N/A')}")
        g = r.get("grid_backtest", {})
        print(f"  Grid Return:    {g.get('total_return_pct', 'N/A')}%")
        print(f"  Grid Win Rate:  {g.get('win_rate_pct', 'N/A')}%")
        print(f"  Grid PF:        {g.get('profit_factor', 'N/A')}")
        print(f"  Grid Max DD:    {g.get('max_dd_pct', 'N/A')}%")
    except Exception as e:
        print(f"  Error parsing: {e}")

# 6. Turtle comparison report
print()
print("=" * 55)
print("TURTLE COMPARISON")
print("=" * 55)
out, _, _ = run("ls -la /home/ubuntu/alphapilot/crypto/turtle_backtest.py 2>/dev/null")
if "No such file" in out or not out:
    out, _, _ = run("ls -la /home/ubuntu/alphapilot/crypto/turtle_backtest.py 2>&1")
print(f"  turtle_backtest.py exists: {'turtle' in out}")

c.close()
print("\nDone.")
