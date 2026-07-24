"""
AlphaPilot 收藏追踪模块
功能：收藏股票、记录入场价、按交易日追踪 T+1/T+2/T+3 收盘涨跌
数据存储：SQLite
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Callable

DB_PATH = Path(__file__).parent / "watchlist.db"


def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# 兼容 api_server 里的 wl_get_db
get_db = _get_db


def init_db():
    conn = _get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 0,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            added_at TEXT NOT NULL,
            entry_price REAL NOT NULL,
            model_score REAL DEFAULT 0,
            day1_price REAL,
            day1_change REAL,
            day1_date TEXT,
            day2_price REAL,
            day2_change REAL,
            day2_date TEXT,
            day3_price REAL,
            day3_change REAL,
            day3_date TEXT,
            status TEXT DEFAULT 'active',
            notes TEXT,
            updated_at TEXT,
            UNIQUE(user_id, symbol)
        )
        """
    )
    # 迁移：老库可能只有 symbol UNIQUE、无 user_id
    cols = {r[1] for r in conn.execute("PRAGMA table_info(watchlist)").fetchall()}
    if "user_id" not in cols:
        conn.execute("ALTER TABLE watchlist ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        # 去掉旧的单列 unique（SQLite 无法直接 DROP CONSTRAINT；用重建）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 0,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                added_at TEXT NOT NULL,
                entry_price REAL NOT NULL,
                model_score REAL DEFAULT 0,
                day1_price REAL,
                day1_change REAL,
                day1_date TEXT,
                day2_price REAL,
                day2_change REAL,
                day2_date TEXT,
                day3_price REAL,
                day3_change REAL,
                day3_date TEXT,
                status TEXT DEFAULT 'active',
                notes TEXT,
                updated_at TEXT,
                UNIQUE(user_id, symbol)
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO watchlist_v2
            (user_id, symbol, name, added_at, entry_price, model_score,
             day1_price, day1_change, day1_date,
             day2_price, day2_change, day2_date,
             day3_price, day3_change, day3_date,
             status, notes, updated_at)
            SELECT 0, symbol, name, added_at, entry_price, model_score,
                   day1_price, day1_change, day1_date,
                   day2_price, day2_change, day2_date,
                   day3_price, day3_change, day3_date,
                   status, notes, updated_at
            FROM watchlist
            """
        )
        conn.execute("DROP TABLE watchlist")
        conn.execute("ALTER TABLE watchlist_v2 RENAME TO watchlist")
    conn.commit()
    conn.close()


def claim_legacy_watchlist(user_id: int) -> int:
    """把 user_id=0 的遗留收藏划归指定用户（通常是站长首次登录）。"""
    init_db()
    conn = _get_db()
    cur = conn.execute(
        "UPDATE watchlist SET user_id = ? WHERE user_id = 0",
        (int(user_id),),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return int(n or 0)


def add_to_watchlist(
    symbol: str,
    name: str,
    entry_price: float,
    model_score: float = 0.0,
    notes: str = "",
    user_id: int = 0,
) -> dict:
    init_db()
    conn = _get_db()
    now = datetime.now().isoformat()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO watchlist
               (user_id, symbol, name, added_at, entry_price, model_score, status, notes, updated_at,
                day1_price, day1_change, day1_date,
                day2_price, day2_change, day2_date,
                day3_price, day3_change, day3_date)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?,
                       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)""",
            (int(user_id), symbol, name, now, entry_price, model_score, notes, now),
        )
        conn.commit()
        result = {
            "symbol": symbol,
            "name": name,
            "entry_price": entry_price,
            "model_score": model_score,
            "added_at": now,
            "status": "active",
            "user_id": int(user_id),
        }
    except Exception as e:
        result = {"error": str(e)}
    finally:
        conn.close()
    return result


def remove_from_watchlist(symbol: str, user_id: int = 0) -> dict:
    init_db()
    conn = _get_db()
    cursor = conn.execute(
        "DELETE FROM watchlist WHERE symbol = ? AND user_id = ?",
        (symbol, int(user_id)),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return {"deleted": deleted, "symbol": symbol}


def get_watchlist(status: str = "all", user_id: int = 0) -> list:
    init_db()
    conn = _get_db()
    if status == "all":
        rows = conn.execute(
            "SELECT * FROM watchlist WHERE user_id = ? ORDER BY added_at DESC",
            (int(user_id),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM watchlist WHERE user_id = ? AND status = ? ORDER BY added_at DESC",
            (int(user_id), status),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _bare(symbol: str) -> str:
    s = str(symbol or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return "".join(ch for ch in s if ch.isdigit())[-6:]


def _parse_added_date(added_at: str) -> date:
    return datetime.fromisoformat(added_at).date()


def _is_weekday(d: date | None = None) -> bool:
    d = d or date.today()
    return d.weekday() < 5


def _session_started(now: datetime | None = None) -> bool:
    """A 股连续竞价已开始（≥09:30）。"""
    now = now or datetime.now()
    return (now.hour, now.minute) >= (9, 30)


def _after_close(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    return (now.hour, now.minute) >= (15, 5)


def _live_close_today(symbol: str) -> tuple[date, float] | None:
    """盘中/盘后用实时价充当「今日」收盘占位，便于 T+n 当日可见。"""
    try:
        from enriched_data import get_quote

        q = get_quote(_bare(symbol), max_age_seconds=60)
        if not q:
            return None
        px = float(q.get("price") or 0)
        if px <= 0:
            return None
        return date.today(), round(px, 4)
    except Exception:
        return None


def _fetch_closes(symbol: str, start: date) -> list[tuple[date, float]]:
    """返回 [(交易日, 收盘价), ...]，仅包含 start 之后的交易日（不含 start 当天）。

    若下一根应是「今天」且日 K 尚未入库（盘中常见），用实时价补一根临时点；
    收盘后 cron 会用正式日 K 覆盖。
    """
    start_s = start.strftime("%Y%m%d")
    try:
        from data_fetcher import get_kline_sina

        df = get_kline_sina(_bare(symbol), start_date=start_s)
    except Exception:
        df = None

    out: list[tuple[date, float]] = []
    if df is not None and not getattr(df, "empty", True):
        cols = {c.lower(): c for c in df.columns}
        date_col = cols.get("date") or cols.get("day") or cols.get("交易日期") or list(df.columns)[0]
        close_col = cols.get("close") or cols.get("收盘") or cols.get("close_price")
        if close_col is None:
            for c in df.columns:
                if "close" in str(c).lower() or str(c) == "收盘":
                    close_col = c
                    break
        if close_col is not None:
            for _, r in df.iterrows():
                raw = r[date_col]
                try:
                    if hasattr(raw, "to_pydatetime"):
                        d = raw.to_pydatetime().date()
                    elif hasattr(raw, "date") and callable(getattr(raw, "date")):
                        d = raw.date()
                    else:
                        s = str(raw)[:10].replace("/", "-")
                        d = datetime.strptime(s, "%Y-%m-%d").date()
                    if not isinstance(d, date):
                        d = date(d.year, d.month, d.day)
                except Exception:
                    continue
                if d <= start:
                    continue
                try:
                    px = float(r[close_col])
                except Exception:
                    continue
                if px > 0:
                    out.append((d, px))

    out.sort(key=lambda x: x[0])

    # 盘中：日 K 还没有「今天」时，用实时价补上，让 T+n 当天就能显示
    today = date.today()
    if (
        _is_weekday(today)
        and _session_started()
        and today > start
        and (not out or out[-1][0] < today)
    ):
        live = _live_close_today(symbol)
        if live and live[0] > start:
            out.append(live)
            out.sort(key=lambda x: x[0])

    return out


def _change_pct(price: float, entry: float) -> float:
    if not entry:
        return 0.0
    return round((price - entry) / entry * 100, 2)


def recompute_tracking(force: bool = True) -> dict:
    """
    用日 K 按交易日重算 T+1/T+2/T+3。
    T+n = 加入日之后的第 n 个交易日收盘价相对入场价涨跌。
    force=True 时覆盖已有 day* 字段（纠错）；False 时只补空缺。
    盘中若日 K 缺「今天」，用实时价预填，收盘后 cron 再固化。
    """
    conn = _get_db()
    rows = conn.execute("SELECT * FROM watchlist").fetchall()
    now = datetime.now()
    updated = 0
    filled = {"day1": 0, "day2": 0, "day3": 0}
    errors: list[str] = []
    provisional = 0

    for row in rows:
        row = dict(row)
        symbol = row["symbol"]
        entry = float(row["entry_price"] or 0)
        if entry <= 0:
            errors.append(f"{symbol}: bad entry")
            continue

        try:
            added = _parse_added_date(row["added_at"])
        except Exception as e:
            errors.append(f"{symbol}: bad added_at ({e})")
            continue

        try:
            closes = _fetch_closes(symbol, added)
        except Exception as e:
            errors.append(f"{symbol}: kline {e}")
            continue

        if not closes and not force:
            continue

        updates: dict = {"updated_at": now.isoformat()}
        today = now.date()

        for i, key in enumerate(("day1", "day2", "day3"), start=1):
            price_k = f"{key}_price"
            chg_k = f"{key}_change"
            date_k = f"{key}_date"
            existing = row.get(price_k)
            if existing is not None and not force:
                continue
            if len(closes) < i:
                continue
            d, px = closes[i - 1]
            # 盘中预填的「今日」点：标记 provisional，允许收盘后再覆盖
            is_prov = d == today and not _after_close(now)
            if is_prov:
                provisional += 1
            updates[price_k] = round(px, 4)
            updates[chg_k] = _change_pct(px, entry)
            updates[date_k] = d.isoformat()
            filled[key] += 1

        day3_final = updates.get("day3_price", row.get("day3_price"))
        # 仅在非预填（已收盘日）凑齐 T+3 才标 completed；今日预填不算完工
        day3_date = updates.get("day3_date", row.get("day3_date"))
        completed_ok = day3_final is not None and day3_date and str(day3_date)[:10] < today.isoformat()
        if day3_final is not None and day3_date and str(day3_date)[:10] == today.isoformat() and _after_close(now):
            completed_ok = True
        updates["status"] = "completed" if completed_ok else "active"

        if len(updates) > 1:
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            rid = row.get("id")
            if rid is not None:
                values = list(updates.values()) + [rid]
                conn.execute(f"UPDATE watchlist SET {set_clause} WHERE id = ?", values)
            else:
                values = list(updates.values()) + [symbol, int(row.get("user_id") or 0)]
                conn.execute(
                    f"UPDATE watchlist SET {set_clause} WHERE symbol = ? AND user_id = ?",
                    values,
                )
            updated += 1

    conn.commit()
    conn.close()
    return {
        "updated": updated,
        "filled": filled,
        "provisional_live": provisional,
        "errors": errors[:20],
        "error_count": len(errors),
        "total": len(rows),
        "force": force,
        "as_of": now.isoformat(),
    }


def update_prices(price_fetcher_func: Optional[Callable] = None) -> dict:
    """兼容旧接口：忽略实时 quote，改为按 K 线重算并补全。"""
    return recompute_tracking(force=True)


init_db()


if __name__ == "__main__":
    print(recompute_tracking(force=True))
