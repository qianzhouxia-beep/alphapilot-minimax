"""v2.49/v2.20 addendum: log feed abr window (win=N) + fix stale caliber
docstrings. LOGGING-ONLY, same version (rule 6: no version bump for
config/comment-level change; decision logic unchanged). CRLF preserved.
"""
import ast
import io
import pathlib

BASE = pathlib.Path("/Users/AlphaPilot/production_strategies")
A = BASE / "track_a" / "TrackA_track_a_qmt_full_chain_sim_v2.49.py"
B = BASE / "track_b" / "TrackB_track_b_qmt_auction_sim_v2.20.py"


def patch(path, repls):
    raw = path.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8")
    if crlf:
        text = text.replace("\r\n", "\n")
    for i, (old, new) in enumerate(repls):
        n = text.count(old)
        if n != 1:
            raise SystemExit("ABORT %s repl#%d count=%d" % (path.name, i, n))
        text = text.replace(old, new)
    out = text.replace("\n", "\r\n") if crlf else text
    data = out.encode("utf-8")
    data.decode("ascii")  # QMT must be pure ASCII
    ast.parse(data.decode("ascii"))
    path.write_bytes(data)
    print("OK %s -> %d bytes CRLF=%s" % (path.name, len(data), crlf))


# ---------------------------------------------------------------- Track A
A_FUNC_OLD = '''def _get_active_buy_from_mootdx(code):
    """Read day-cumulative active-buy ratio from mootdx_feed local JSON.

    mootdx_feed.py runs as a separate process and writes
    {MOOTDX_FEED_DIR}/{YYYYMMDD}.json = {code: {abr, buy_vol, sell_vol, ts, n}}.
    abr is cumulative over the session (transaction() returns the day's ticks)
    -> same bucket-free cumulative semantics as the backtest P2_cum gate.
    Returns (abr, age_sec) or (None, None) when no fresh entry.
    """
    if not USE_MOOTDX_ACTIVE_BUY:
        return None, None
    try:
        today = datetime.now().strftime("%Y%m%d")
        p = os.path.join(MOOTDX_FEED_DIR, today + ".json")
        if not os.path.exists(p):
            return None, None
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        rec = data.get(code)
        if not rec:
            return None, None
        ts = rec.get("ts", 0)
        age = time.time() - ts
        if age > MOOTDX_FEED_MAX_AGE_SEC:
            return None, age
        abr = rec.get("abr")
        if abr is None:
            return None, age
        return float(abr), age
    except BaseException:
        return None, None
'''

A_FUNC_NEW = '''def _get_active_buy_from_mootdx(code):
    """Read the active-buy ratio from the l2_feed local JSON.

    The feed runs as a separate process and writes
    {MOOTDX_FEED_DIR}/{YYYYMMDD}.json = {code: {abr, buy_vol, sell_vol, ts, n}}.
    Producer is pluggable (mootdx_feed, or tencent_tick_feed since 2026-09-15);
    this reader only consumes ts + abr, so the producer does not matter here.
    NOTE (v2.49 addendum): the OLD mootdx producer was day-cumulative, but the
    tencent replacement defines abr over the LAST n ticks (n=800 rolling), which
    may differ from the day-cumulative P2_cum window that MIN_ACTIVE_BUY=0.52
    was calibrated on. n is returned as win so P2 logs/items can carry it.
    Returns (abr, age_sec, win) or (None, ...) when no fresh entry.
    """
    if not USE_MOOTDX_ACTIVE_BUY:
        return None, None, None
    try:
        today = datetime.now().strftime("%Y%m%d")
        p = os.path.join(MOOTDX_FEED_DIR, today + ".json")
        if not os.path.exists(p):
            return None, None, None
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        rec = data.get(code)
        if not rec:
            return None, None, None
        ts = rec.get("ts", 0)
        age = time.time() - ts
        if age > MOOTDX_FEED_MAX_AGE_SEC:
            return None, age, None
        abr = rec.get("abr")
        if abr is None:
            return None, age, None
        return float(abr), age, rec.get("n")
    except BaseException:
        return None, None, None
'''

A_REPLS = [
    # header addendum
    (
        "#   Now: abr out of [0,1] or src!=mootdx -> fail-open (treat as missing);\n"
        "#   the calibrated hard gate stays for mootdx. SIM only; live tpl untouched.\n",
        "#   Now: abr out of [0,1] or src!=feed -> fail-open (treat as missing);\n"
        "#   the calibrated hard gate stays for the feed channel. SIM only; live\n"
        "#   tpl untouched.\n"
        "#   v2.49 addendum (same version, LOGGING-ONLY; not yet deployed): the\n"
        "#   feed producer switched mootdx -> tencent_tick_feed (2026-09-15) whose\n"
        "#   abr window is the LAST 800 ticks (rolling), NOT the day-cumulative\n"
        "#   P2_cum window that 0.52 was calibrated on (E20: window caliber >\n"
        "#   threshold). The guard fixes the L1-vs-feed SOURCE mismatch only, not\n"
        "#   this WINDOW mismatch. No recalibration here (no same-day TDX vs\n"
        "#   tencent comparison yet); instead P2 abr logs and the item now carry\n"
        "#   the feed window length (win=N from the feed's n field) so E23\n"
        "#   (P2_cum approx re-verify) and any future recalibration have direct\n"
        "#   evidence. Decision logic unchanged.\n",
    ),
    # config comment block
    (
        "# --- ABR (active-buy ratio) gate v2.13 (Level-2 style via mootdx feed) ---\n"
        "# Backtest 2026-08 (114 candidates / 20 days, real Top10 archives):\n"
        "#   cumulative ABR >= 0.52 at the P2 trigger lifts T+1 winrate 42.3% -> 54.2%,\n"
        "#   T+1 mean -0.46% -> +0.36% (low ABR = weak buy force -> filter).\n"
        "# Source priority: mootdx_feed (separate process, free TDX tick direction,\n"
        "# day-cumulative, matches backtest P2_cum) -> QMT L1 tick approx (last 120\n"
        "# ticks, trade px>=ask1=buy). SOFT gate: ABR unavailable -> pass, so a feed\n"
        "# outage never freezes buying.\n",
        "# --- ABR (active-buy ratio) gate v2.13 (Level-2 style via l2_feed file) ---\n"
        "# Backtest 2026-08 (114 candidates / 20 days, real Top10 archives):\n"
        "#   cumulative ABR >= 0.52 at the P2 trigger lifts T+1 winrate 42.3% -> 54.2%,\n"
        "#   T+1 mean -0.46% -> +0.36% (low ABR = weak buy force -> filter).\n"
        "# Source priority: l2_feed file channel (separate process; was mootdx_feed,\n"
        "# now tencent_tick_feed since 2026-09-15). NOTE: the replacement's abr is a\n"
        "# last-800-tick rolling window, NOT necessarily the day-cumulative P2_cum\n"
        "# window that 0.52 was calibrated on; P2 logs/items carry win=N to keep\n"
        "# this auditable (E20). Then QMT L1 tick approx (last 120 ticks, trade\n"
        "# px>=ask1=buy). SOFT gate: ABR unavailable -> pass, so a feed outage never\n"
        "# freezes buying.\n",
    ),
    # config constant
    (
        "# v2.49: apply MIN_ACTIVE_BUY only when abr is from the calibrated caliber\n"
        "# (mootdx day-cumulative ticks). L1 120-tick fallback is uncalibrated.\n"
        "ABR_CALIBRATED_SRC_ONLY = True\n",
        "# v2.49: apply MIN_ACTIVE_BUY only when abr is from the calibrated caliber\n"
        "# (the l2_feed file channel). L1 120-tick fallback is uncalibrated.\n"
        "ABR_CALIBRATED_SRC_ONLY = True\n"
        "# v2.49 addendum: canonical label of the calibrated feed channel, logged\n"
        "# as src=<this>. Producer-agnostic (the reader reads the file, not the\n"
        "# process).\n"
        'ABR_CALIBRATED_SRC = "feed"\n',
    ),
    # reader function
    (A_FUNC_OLD, A_FUNC_NEW),
    # verdict docstring
    (
        "    'open_uncal' - below floor but non-mootdx caliber -> fail-open (no veto)\n",
        "    'open_uncal' - below floor but non-feed caliber -> fail-open (no veto)\n",
    ),
    # verdict condition
    (
        '        if ABR_CALIBRATED_SRC_ONLY and abr_src != "mootdx":\n',
        "        if ABR_CALIBRATED_SRC_ONLY and abr_src != ABR_CALIBRATED_SRC:\n",
    ),
    # ratio unpack
    (
        "    abr, age = _get_active_buy_from_mootdx(code)\n"
        "    if abr is not None:\n"
        "        return abr\n",
        "    abr, age, _win = _get_active_buy_from_mootdx(code)\n"
        "    if abr is not None:\n"
        "        return abr\n",
    ),
    # ratio docstring
    (
        '    """Active buy ratio: mootdx real ticks first, then QMT L1 tick approx.\n'
        "\n"
        "    mootdx feed (free TDX per-tick buy/sell direction) preferred when fresh.\n",
        '    """Active buy ratio: l2_feed file first, then QMT L1 tick approx.\n'
        "\n"
        "    l2_feed file channel (free per-tick buy/sell direction) preferred when\n"
        "    fresh.\n",
    ),
    # p2_decide src + logs
    (
        "            abr = _get_active_buy_ratio(C, code)\n"
        "            src_m, _age = _get_active_buy_from_mootdx(code)\n"
        "            if src_m is not None:\n"
        '                abr_src = "mootdx"\n'
        "            elif abr is not None:\n"
        '                abr_src = "l1"\n'
        "            else:\n"
        '                abr_src = "none"\n'
        "            # v2.49 abr caliber guard (see header).\n"
        "            _v = _abr_verdict(abr, abr_src)\n"
        '            if _v == "open_oob":\n'
        '                print("[P2] abr out-of-range -> fail-open " + str(code) + " abr=" +\n'
        '                      str(round(abr, 4)) + " src=" + abr_src, flush=True)\n'
        '            elif _v == "open_uncal":\n'
        '                print("[P2] abr uncalibrated -> fail-open " + str(code) + " abr=" +\n'
        '                      str(round(abr, 4)) + " src=" + abr_src, flush=True)\n'
        '            elif _v == "skip":\n'
        '                print("[P2] skip_low_abr " + str(code) + " abr=" +\n'
        '                      str(round(abr, 4)) + " src=" + abr_src, flush=True)\n'
        '                return None, "skip_low_abr"\n',
        "            abr = _get_active_buy_ratio(C, code)\n"
        "            src_m, _age, win_m = _get_active_buy_from_mootdx(code)\n"
        "            if src_m is not None:\n"
        "                abr_src = ABR_CALIBRATED_SRC\n"
        "            elif abr is not None:\n"
        '                abr_src = "l1"\n'
        "            else:\n"
        '                abr_src = "none"\n'
        "            # v2.49 addendum: record channel + feed window length (E23).\n"
        "            if item is not None:\n"
        '                item["abr_src"] = abr_src\n'
        '                item["abr_win"] = win_m\n'
        '            _wt = (" win=" + str(win_m)) if win_m else ""\n'
        "            # v2.49 abr caliber guard (see header).\n"
        "            _v = _abr_verdict(abr, abr_src)\n"
        '            if _v == "open_oob":\n'
        '                print("[P2] abr out-of-range -> fail-open " + str(code) + " abr=" +\n'
        '                      str(round(abr, 4)) + " src=" + abr_src + _wt, flush=True)\n'
        '            elif _v == "open_uncal":\n'
        '                print("[P2] abr uncalibrated -> fail-open " + str(code) + " abr=" +\n'
        '                      str(round(abr, 4)) + " src=" + abr_src + _wt, flush=True)\n'
        '            elif _v == "skip":\n'
        '                print("[P2] skip_low_abr " + str(code) + " abr=" +\n'
        '                      str(round(abr, 4)) + " src=" + abr_src + _wt, flush=True)\n'
        '                return None, "skip_low_abr"\n',
    ),
]

# ---------------------------------------------------------------- Track B
B_FUNC_OLD = '''def _get_active_buy_from_mootdx(code):
    """Read active-buy ratio from mootdx_feed local JSON.

    Returns (abr, age_sec) or (None, None) when no fresh entry.
    Falls back naturally: caller uses L1 tick approximation if None.
    """
    if not USE_MOOTDX_ACTIVE_BUY:
        return None, None
    try:
        today = datetime.now().strftime("%Y%m%d")
        p = os.path.join(MOOTDX_FEED_DIR, today + ".json")
        if not os.path.exists(p):
            return None, None
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        rec = data.get(code)
        if not rec:
            return None, None
        ts = rec.get("ts", 0)
        age = time.time() - ts
        if age > MOOTDX_FEED_MAX_AGE_SEC:
            return None, age
        abr = rec.get("abr")
        if abr is None:
            return None, age
        return float(abr), age
    except BaseException:
        return None, None
'''

B_FUNC_NEW = '''def _get_active_buy_from_mootdx(code):
    """Read the active-buy ratio from the l2_feed local JSON.

    Producer is pluggable (mootdx_feed, or tencent_tick_feed since 2026-09-15);
    this reader only consumes ts + abr, so the producer does not matter here.
    NOTE (v2.20 addendum): the tencent replacement defines abr over the LAST n
    ticks (n=800 rolling), which may differ from the day-cumulative P2_cum
    window that MIN_ACTIVE_BUY=0.52 was calibrated on. n is returned as win so
    the item and [P2] logs can carry it.
    Returns (abr, age_sec, win) or (None, ...) when no fresh entry.
    Falls back naturally: caller uses L1 tick approximation if None.
    """
    if not USE_MOOTDX_ACTIVE_BUY:
        return None, None, None
    try:
        today = datetime.now().strftime("%Y%m%d")
        p = os.path.join(MOOTDX_FEED_DIR, today + ".json")
        if not os.path.exists(p):
            return None, None, None
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        rec = data.get(code)
        if not rec:
            return None, None, None
        ts = rec.get("ts", 0)
        age = time.time() - ts
        if age > MOOTDX_FEED_MAX_AGE_SEC:
            return None, age, None
        abr = rec.get("abr")
        if abr is None:
            return None, age, None
        return float(abr), age, rec.get("n")
    except BaseException:
        return None, None, None
'''

B_REPLS = [
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
    (
        '    """active buy ratio: mootdx real ticks first, then QMT L1 tick approx.\n'
        "\n"
        "    mootdx feed (free TDX transaction ticks) gives real per-tick buy/sell\n"
        "    direction; prefer it when fresh. Fall back to QMT L1 tick approximation\n"
        "    (trade price >= ask1 -> buy; <= bid1 -> sell) when feed missing/stale.\n"
        '    """\n'
        "    abr, age = _get_active_buy_from_mootdx(code)\n",
        '    """active buy ratio: l2_feed file first, then QMT L1 tick approx.\n'
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

if 'ABR_CALIBRATED_SRC = "feed"' in A.read_text(encoding="utf-8"):
    print("SKIP A (already patched)")
else:
    patch(A, A_REPLS)
patch(B, B_REPLS)
print("DONE")
