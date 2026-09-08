# -*- coding: utf-8 -*-
"""查服务器 5m 数据可用性 (一次性)"""
import sys
sys.path.insert(0, r"C:/Users/elvisq/Projects/alphapilot/bt_research")
from srv_ssh import Ssh

CMD = r"""
cd /home/ubuntu/alphapilot && ls -la data/kline5m_cache/ 2>/dev/null | head -20; echo '---'; ls data/ 2>/dev/null | grep -i -E '5m|min|kline' | head
"""

s = Ssh()
try:
    o, e, code = s.run(CMD, timeout=60)
    print(o)
    if e.strip():
        print("ERR:", e[:400])
finally:
    s.close()
