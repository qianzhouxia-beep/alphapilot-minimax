#!/usr/bin/env python3
from datetime import datetime
from k_execution import apply_entry_timing, time_stop_triggered, ticket_exec_meta

print(apply_entry_timing({"action": "buy", "gap": 0.01}, now=datetime(2026, 7, 22, 10, 0)))
print(apply_entry_timing({"action": "buy", "gap": 0.01}, now=datetime(2026, 7, 22, 9, 28)))
print(time_stop_triggered({"trailing_high": 10}, price=9.95, cost=10, held_days=1, can_sell=True))
print(ticket_exec_meta())
print("ok")
