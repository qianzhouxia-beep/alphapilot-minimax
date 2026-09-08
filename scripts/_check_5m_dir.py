# -*- coding: utf-8 -*-
"""查服务器 kline5m 目录结构 (一次性)"""
import sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

CMD = r"""
cd /home/ubuntu/alphapilot && ls -la data/kline5m/ 2>/dev/null | head -30; echo '=== kline5m_hist ==='; ls -la data/kline5m_hist/ 2>/dev/null | head -30
"""

s = Ssh()
try:
    o, e, code = s.run(CMD, timeout=60)
    print(o)
    if e.strip():
        print("ERR:", e[:400])
finally:
    s.close()
