#!/usr/bin/env python3
"""AlphaPilot Crypto — 24/7 仿真交易监控驾驶舱 (zero-dependency web server).

Reads the paper trader's state files and serves a self-refreshing dashboard:
  - account overview (capital, equity, PnL, win rate, drawdown)
  - equity curve (time series from paper_equity.jsonl)
  - open positions + closed trade history
  - daily PnL (today / yesterday / last 24h)
  - attribution (by direction / symbol / exit reason / session / hold bucket)
  - learning / adaptive state + guardrail history

Run:
  python3 crypto/dashboard.py            # serves on 0.0.0.0:8899
No third-party deps. Pure stdlib.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "output" / "crypto"
HTML_PATH = Path(__file__).resolve().parent / "dashboard.html"
PORT = int(os.environ.get("CRYPTO_DASH_PORT", "8899"))

STATE_PATH = MODEL_DIR / "paper_state.json"
EQUITY_PATH = MODEL_DIR / "paper_equity.jsonl"
REPORT_PATH = MODEL_DIR / "sg_server_report.json"
LEARNING_PATH = MODEL_DIR / "learning_report.json"
ADAPT_PATH = MODEL_DIR / "adaptive_state.json"
GUARD_HIST = MODEL_DIR / "guardrail_history.jsonl"
SIGNAL_PATH = MODEL_DIR / "signal.json"


def _load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def _sym(s: str) -> str:
    return str(s).replace("/USDT:USDT", "")


def _parse_ts(s):
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    except Exception:
        return None


def _equity_series():
    """Read paper_equity.jsonl -> list of {ts, equity, capital, positions}."""
    out = []
    try:
        for line in EQUITY_PATH.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            out.append({
                "ts": d.get("ts", ""),
                "equity": round(float(d.get("equity", 0)), 2),
                "capital": round(float(d.get("capital", 0)), 2),
                "positions": d.get("positions", 0),
            })
    except Exception:
        pass
    return out


def _trades_stats(trades, start=None, end=None):
    pnl = 0.0
    wins = losses = 0
    for t in trades:
        ts = _parse_ts(t.get("exit_time", ""))
        if start is not None and (ts is None or ts < start):
            continue
        if end is not None and (ts is None or ts >= end):
            continue
        p = float(t.get("pnl_usdt", 0) or 0)
        pnl += p
        if p > 0:
            wins += 1
        else:
            losses += 1
    n = wins + losses
    return {"n": n, "pnl": round(pnl, 2), "wins": wins, "losses": losses,
            "win_rate": round(100 * wins / n, 1) if n else 0}


def _group_stats(trades, keyfn):
    buckets = {}
    for t in trades:
        k = keyfn(t)
        buckets.setdefault(k, []).append(t)
    out = {}
    for k, ts in sorted(buckets.items()):
        s = _trades_stats(ts)
        out[k] = s
    return out


def build_payload() -> dict:
    state = _load(STATE_PATH)
    report = _load(REPORT_PATH)
    learning = _load(LEARNING_PATH)
    adaptive = _load(ADAPT_PATH)
    signal = _load(SIGNAL_PATH)

    trades = state.get("trades", [])
    positions = state.get("positions", [])
    last_px = state.get("last_price_by_sym", {})
    initial = float(state.get("initial_capital", 1000.0))
    capital = float(state.get("capital", initial))

    # open positions with live unrealized PnL
    open_upnl = 0.0
    open_rows = []
    for p in positions:
        sym = _sym(p.get("symbol", ""))
        px = last_px.get(p.get("symbol"))
        dirn = p.get("direction", "?")
        size = float(p.get("batch_size", 0))
        if px:
            upnl_pct = (px / float(p["entry_price"]) - 1) * (1 if dirn == "long" else -1)
            upnl = size * upnl_pct
            open_upnl += upnl
        else:
            upnl_pct = upnl = 0.0
        try:
            et = datetime.fromisoformat(str(p["entry_time"]))
            if et.tzinfo is not None:
                et = et.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            et = datetime.now()
        hold_h = round((datetime.now() - et).total_seconds() / 3600, 1) if et else 0
        open_rows.append({
            "symbol": sym, "direction": dirn, "entry_price": round(float(p["entry_price"]), 4),
            "size": round(size, 2), "level": p.get("level", 0),
            "upnl_pct": round(upnl_pct * 100, 2), "upnl": round(upnl, 2),
            "hold_h": hold_h, "entry_score": p.get("entry_score"),
        })

    equity = capital + open_upnl
    total_pnl = sum(float(t.get("pnl_usdt", 0) or 0) for t in trades)
    wins = sum(1 for t in trades if (t.get("pnl_usdt", 0) or 0) > 0)
    total_fees = sum(float(t.get("fee_usdt", 0) or 0) for t in trades)
    n = len(trades)

    now = datetime.now(timezone.utc)
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yday0 = today0 - timedelta(days=1)
    today_s = _trades_stats(trades, today0, None)
    yesterday_s = _trades_stats(trades, yday0, today0)
    last24_s = _trades_stats(trades, now - timedelta(hours=24), None)

    # max drawdown on equity series
    eq = _equity_series()
    eq_vals = [e["equity"] for e in eq]
    peak = 0.0
    max_dd = 0.0
    for v in eq_vals:
        peak = max(peak, v)
        if peak > 0:
            max_dd = min(max_dd, v / peak - 1)

    recent = []
    for t in trades[-40:][::-1]:
        recent.append({
            "symbol": _sym(t.get("symbol", "")), "direction": t.get("direction", "?"),
            "entry_price": round(float(t.get("entry_price", 0)), 4),
            "exit_price": round(float(t.get("exit_price", 0)), 4),
            "pnl_pct": round(float(t.get("pnl_pct", 0)) * 100, 2),
            "pnl": round(float(t.get("pnl_usdt", 0)), 2),
            "exit_time": str(t.get("exit_time", ""))[:16],
            "exit_reason": t.get("exit_reason", "?"),
            "score": t.get("entry_score"),
            "fee": round(float(t.get("fee_usdt", 0)), 3),
        })

    guard_hist = []
    try:
        for line in GUARD_HIST.read_text(encoding="utf-8").strip().splitlines():
            if line.strip():
                try:
                    guard_hist.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass

    return {
        "asof": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "state": {
            "initial_capital": initial, "capital": round(capital, 2),
            "equity": round(equity, 2), "open_pnl": round(open_upnl, 2),
            "open_positions": len(positions), "closed_trades": n,
            "total_entries": state.get("total_entries", 0),
            "total_exits": state.get("total_exits", 0),
            "last_bar": state.get("last_bar_ts", ""),
            "smc": state.get("smc", {}),
        },
        "stats": {
            "total_pnl": round(total_pnl, 2), "win_rate": round(100 * wins / n, 1) if n else 0,
            "n_wins": wins, "n_losses": n - wins, "total_fees": round(total_fees, 2),
            "today": today_s, "yesterday": yesterday_s, "last24h": last24_s,
            "max_drawdown_pct": round(max_dd * 100, 2),
        },
        "equity_curve": eq[-500:],
        "by_direction": _group_stats(trades, lambda t: t.get("direction", "?")),
        "by_symbol": _group_stats(trades, lambda t: _sym(t.get("symbol", "?"))),
        "by_exit_reason": _group_stats(trades, lambda t: t.get("exit_reason", "?")),
        "by_session": learning.get("attribution", {}).get("by_session", {}),
        "by_hold": learning.get("attribution", {}).get("by_hold_bucket", {}),
        "open_positions": open_rows,
        "recent_trades": recent,
        "learning": {
            "flags": learning.get("flags", []),
            "notes": learning.get("adaptive", {}).get("notes", []),
            "asof": learning.get("asof", ""),
        },
        "adaptive": adaptive,
        "guardrail": report.get("guardrail", {}),
        "guardrail_history": guard_hist[-20:],
        "model": {
            "long_auc": report.get("long_auc"),
            "short_auc": report.get("short_auc"),
            "n_factors": report.get("config", {}).get("n_factors"),
            "report_asof": report.get("asof", ""),
        },
        "signals": signal.get("signals", []) if isinstance(signal, dict) else [],
        "signal_asof": signal.get("asof", "") if isinstance(signal, dict) else "",
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/state":
            try:
                payload = build_payload()
                self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif path in ("/", "/index.html"):
            try:
                html = HTML_PATH.read_text(encoding="utf-8")
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            except Exception as e:
                self._send(500, str(e).encode("utf-8"), "text/plain; charset=utf-8")
        elif path == "/logo.png":
            logo = Path(__file__).resolve().parent / "logo.png"
            try:
                self._send(200, logo.read_bytes(), "image/png")
            except Exception:
                self._send(404, b"not found", "text/plain")
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, fmt, *args):
        pass


def main():
    print(f"AlphaPilot Crypto Dashboard — http://0.0.0.0:{PORT}")
    print(f"Reading from {MODEL_DIR}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
