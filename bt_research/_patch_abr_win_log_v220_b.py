"""B-only v2.20 win= log fold-in (companion to A already patched)."""
import ast
import pathlib

B = pathlib.Path(
    "/Users/AlphaPilot/production_strategies/track_b/"
    "TrackB_track_b_qmt_auction_sim_v2.20.py")

B_FUNC_OLD = (
    'def _get_active_buy_from_mootdx(code):\n'
    '    """Read active-buy ratio from mootdx_feed local JSON.\n'
    "\n"
    "    Returns (abr, age_sec) or (None, None) when no fresh entry.\n"
    "    Falls back naturally: caller uses L1 tick approximation if None.\n"
    '    """\n'
    "    if not USE_MOOTDX_ACTIVE_BUY:\n"
    "        return None, None\n"
    "    try:\n"
    '        today = datetime.now().strftime("%Y%m%d")\n'
    "        p = os.path.join(MOOTDX_FEED_DIR, today + \".json\")\n"
    "        if not os.path.exists(p):\n"
    "            return None, None\n"
    '        with open(p, "r", encoding="utf-8") as f:\n'
    "            data = json.load(f)\n"
    "        rec = data.get(code)\n"
    "        if not rec:\n"
    "            return None, None\n"
    '        ts = rec.get("ts", 0)\n'
    "        age = time.time() - ts\n"
    "        if age > MOOTDX_FEED_MAX_AGE_SEC:\n"
    "            return None, age\n"
    '        abr = rec.get("abr")\n'
    "        if abr is None:\n"
    "            return None, age\n"
    "        return float(abr), age\n"
    "    except BaseException:\n"
    "        return None, None\n"
)

B_FUNC_NEW = (
    'def _get_active_buy_from_mootdx(code):\n'
    '    """Read the active-buy ratio from the l2_feed local JSON.\n'
    "\n"
    "    Producer is pluggable (mootdx_feed, or tencent_tick_feed since 2026-09-15);\n"
    "    this reader only consumes ts + abr, so the producer does not matter here.\n"
    "    NOTE (v2.20 addendum): the tencent replacement defines abr over the LAST n\n"
    "    ticks (n=800 rolling), which may differ from the day-cumulative P2_cum\n"
    "    window that MIN_ACTIVE_BUY=0.52 was calibrated on. n is returned as win so\n"
    "    the item and [P2] logs can carry it.\n"
    "    Returns (abr, age_sec, win) or (None, ...) when no fresh entry.\n"
    "    Falls back naturally: caller uses L1 tick approximation if None.\n"
    '    """\n'
    "    if not USE_MOOTDX_ACTIVE_BUY:\n"
    "        return None, None, None\n"
    "    try:\n"
    '        today = datetime.now().strftime("%Y%m%d")\n'
    "        p = os.path.join(MOOTDX_FEED_DIR, today + \".json\")\n"
    "        if not os.path.exists(p):\n"
    "            return None, None, None\n"
    '        with open(p, "r", encoding="utf-8") as f:\n'
    "            data = json.load(f)\n"
    "        rec = data.get(code)\n"
    "        if not rec:\n"
    "            return None, None, None\n"
    '        ts = rec.get("ts", 0)\n'
    "        age = time.time() - ts\n"
    "        if age > MOOTDX_FEED_MAX_AGE_SEC:\n"
    "            return None, age, None\n"
    '        abr = rec.get("abr")\n'
    "        if abr is None:\n"
    "            return None, age, None\n"
    '        return float(abr), age, rec.get("n")\n'
    "    except BaseException:\n"
    "        return None, None, None\n"
)

REPLS = [
    # header
    (
        "#     applying 0.52 to it mass-rejected candidates. Now abr out of [0,1] or\n"
        "#     src!=mootdx -> fail-open in BOTH _p2_gate and _p2_decide; calibrated\n"
        "#     hard gate kept for mootdx. SIM-ONLY; live tpl untouched.\n",
        "#     applying 0.52 to it mass-rejected candidates. Now abr out of [0,1] or\n"
        "#     src!=feed -> fail-open in BOTH _p2_gate and _p2_decide; calibrated\n"
        "#     hard gate kept for the feed channel. SIM-ONLY; live tpl untouched.\n"
        "#   * v2.20 addendum (same version, LOGGING-ONLY; not yet deployed): the\n"
        "#     feed producer switched mootdx -> tencent_tick_feed (2026-09-15) whose\n"
        "#     abr window is the LAST 800 ticks (rolling), NOT the day-cumulative\n"
        "#     P2_cum window that 0.52 was calibrated on (E20: window caliber >\n"
        "#     threshold). The guard fixes the L1-vs-feed SOURCE mismatch only, not\n"
        "#     this WINDOW mismatch. No recalibration here; abr_src + abr_win (feed\n"
        "#     n field) are now recorded on the item and in [P2] abr logs for E23.\n",
    ),
    # config
    (
        "MIN_ACTIVE_BUY = 0.52             # active buy ratio floor (QMT HARD; server SOFT)\n"
        "# v2.20: apply the floor only for the calibrated mootdx day-cumulative\n"
        "# caliber; L1 120-tick fallback is uncalibrated -> fail-open.\n"
        "ABR_CALIBRATED_SRC_ONLY = True\n",
        "MIN_ACTIVE_BUY = 0.52             # active buy ratio floor (QMT HARD; server SOFT)\n"
        "# v2.20: apply the floor only for the calibrated l2_feed channel; L1\n"
        "# 120-tick fallback is uncalibrated -> fail-open.\n"
        "ABR_CALIBRATED_SRC_ONLY = True\n"
        "# v2.20 addendum: canonical label of the calibrated feed channel\n"
        "# (src=<this>). Producer-agnostic: reader reads the file, not the process.\n"
        'ABR_CALIBRATED_SRC = "feed"\n',
    ),
    (B_FUNC_OLD, B_FUNC_NEW),
    (
        "    'open_uncal' - below floor but non-mootdx caliber -> fail-open (no veto)\n",
        "    'open_uncal' - below floor but non-feed caliber -> fail-open (no veto)\n",
    ),
    (
        '        if ABR_CALIBRATED_SRC_ONLY and abr_src != "mootdx":\n',
        "        if ABR_CALIBRATED_SRC_ONLY and abr_src != ABR_CALIBRATED_SRC:\n",
    ),
    # ratio docstring + unpack
    (
        '    """active buy ratio: mootdx real ticks first, then L1 tick approx.\n'
        "\n"
        "    mootdx feed (free TDX transaction ticks) gives real per-tick buy/sell\n"
        "    direction; prefer it when fresh. Fall back to QMT L1 tick approximation\n"
        "    (trade price >= ask1 -> buy; <= bid1 -> sell) when feed missing/stale.\n"
        '    """\n'
        "    abr, age = _get_active_buy_from_mootdx(code)\n",
        '    """active buy ratio: l2_feed file first, then L1 tick approx.\n'
        "\n"
        "    The l2_feed file channel gives real per-tick buy/sell direction; prefer\n"
        "    it when fresh. Fall back to QMT L1 tick approximation (trade price >=\n"
        "    ask1 -> buy; <= bid1 -> sell) when feed missing/stale.\n"
        '    """\n'
        "    abr, age, _win = _get_active_buy_from_mootdx(code)\n",
    ),
    # _p2_gate
    (
        "    abr = _get_active_buy_ratio(C, code)\n"
        "    src_m, _age = _get_active_buy_from_mootdx(code)\n"
        "    if src_m is not None:\n"
        '        abr_src = "mootdx"\n'
        "    elif abr is not None:\n"
        '        abr_src = "l1"\n'
        "    else:\n"
        '        abr_src = "none"\n'
        "    # v2.20 abr caliber guard (see header).\n"
        "    _v = _abr_verdict(abr, abr_src)\n"
        '    if _v == "open_oob":\n'
        '        print("[P2] abr out-of-range -> fail-open " + str(code) + " abr="\n'
        '              + str(round(abr, 4)) + " src=" + abr_src, flush=True)\n'
        '    elif _v == "open_uncal":\n'
        '        print("[P2] abr uncalibrated -> fail-open " + str(code) + " abr="\n'
        '              + str(round(abr, 4)) + " src=" + abr_src, flush=True)\n'
        '    elif _v == "skip":\n'
        '        print("[P2] skip_low_abr " + str(code) + " abr=" + str(round(abr, 4))\n'
        '              + " src=" + abr_src, flush=True)\n'
        '        return None, "skip_low_abr"\n',
        "    abr = _get_active_buy_ratio(C, code)\n"
        "    src_m, _age, win_m = _get_active_buy_from_mootdx(code)\n"
        "    if src_m is not None:\n"
        "        abr_src = ABR_CALIBRATED_SRC\n"
        "    elif abr is not None:\n"
        '        abr_src = "l1"\n'
        "    else:\n"
        '        abr_src = "none"\n'
        "    # v2.20 addendum: record channel + feed window length (E23).\n"
        '    it["abr_src"] = abr_src\n'
        '    it["abr_win"] = win_m\n'
        '    _wt = (" win=" + str(win_m)) if win_m else ""\n'
        "    # v2.20 abr caliber guard (see header).\n"
        "    _v = _abr_verdict(abr, abr_src)\n"
        '    if _v == "open_oob":\n'
        '        print("[P2] abr out-of-range -> fail-open " + str(code) + " abr="\n'
        '              + str(round(abr, 4)) + " src=" + abr_src + _wt, flush=True)\n'
        '    elif _v == "open_uncal":\n'
        '        print("[P2] abr uncalibrated -> fail-open " + str(code) + " abr="\n'
        '              + str(round(abr, 4)) + " src=" + abr_src + _wt, flush=True)\n'
        '    elif _v == "skip":\n'
        '        print("[P2] skip_low_abr " + str(code) + " abr=" + str(round(abr, 4))\n'
        '              + " src=" + abr_src + _wt, flush=True)\n'
        '        return None, "skip_low_abr"\n',
    ),
    # _p2_decide
    (
        "            abr = _get_active_buy_ratio(C, code)\n"
        "            src, _age = _get_active_buy_from_mootdx(code)\n"
        '            abr_src = "mootdx" if src is not None else "l1"\n'
        '            it["abr_src"] = abr_src\n',
        "            abr = _get_active_buy_ratio(C, code)\n"
        "            src, _age, win = _get_active_buy_from_mootdx(code)\n"
        '            abr_src = ABR_CALIBRATED_SRC if src is not None else "l1"\n'
        '            it["abr_src"] = abr_src\n'
        '            it["abr_win"] = win\n',
    ),
]

raw = B.read_bytes()
crlf = b"\r\n" in raw
text = raw.decode("utf-8").replace("\r\n", "\n")
for i, (old, new) in enumerate(REPLS):
    n = text.count(old)
    if n != 1:
        raise SystemExit("ABORT B repl#%d count=%d" % (i, n))
    text = text.replace(old, new)
out = text.replace("\n", "\r\n") if crlf else text
data = out.encode("utf-8")
data.decode("ascii")
ast.parse(data.decode("ascii"))
B.write_bytes(data)
print("OK %s -> %d bytes CRLF=%s" % (B.name, len(data), crlf))
