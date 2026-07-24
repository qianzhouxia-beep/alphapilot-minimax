#!/usr/bin/env python3
import sqlite3, json
from pathlib import Path
p = Path("/home/ubuntu/alphapilot/watchlist.db")
conn = sqlite3.connect(str(p))
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT symbol,name,added_at,entry_price,day1_price,day1_change,day1_date,day2_price,day2_change,day2_date,day3_price,day3_change,day3_date,status,updated_at FROM watchlist ORDER BY added_at DESC").fetchall()
for r in rows:
    print(json.dumps(dict(r), ensure_ascii=False))
print("COUNT", len(rows))
