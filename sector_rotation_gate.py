#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板块资金轮动硬门控（行业骨架 + 概念锋面，1–3 日快轮动）。

设计原则:
  - 行业（通达信）定骨架；概念（通达信题材）定锋面
  - 只做通过/拒绝，不改 score
  - 行业大撤退 → 拒绝；主概念大额流出 → 拒绝
  - 行业中性但概念流入 → 可保留（轮动锋面）

数据:
  - 行业流: akshare / data/sector_flow_today.json|3day.json
  - 概念流: akshare.stock_fund_flow_concept / data/concept_flow_today.json|3day.json
  - 股票→行业: data/stock_industry_map.json
  - 股票→概念: data/stock_concept_map.json
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
DATA = ROOT / "data"
SNAP = OUT / "sector_rotation_snapshot.json"
MAP_PATH = DATA / "stock_industry_map.json"
CONCEPT_MAP_PATH = DATA / "stock_concept_map.json"

# 名称模糊归并：个股行业字段与东财板块名不完全一致时用
TECH_WEAK_KEYWORDS = (
    "半导体",
    "消费电子",
    "IT服务",
    "软件开发",
    "计算机",
    "通信设备",
    "元件",
    "光学光电子",
    "电子",
    "游戏",
    "互联网",
)


def _bare(sym: str) -> str:
    s = str(sym or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
    return s[-6:]


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _ak_flow_table(fn_name: str, source: str) -> list[dict]:
    import akshare as ak

    last_err = None
    for attempt in range(3):
        try:
            df = getattr(ak, fn_name)()
            rows = []
            for _, r in df.iterrows():
                name = str(r.get("行业") or r.get("概念") or r.get("名称") or "").strip()
                if not name:
                    continue
                rows.append(
                    {
                        "name": name,
                        "net_yi": float(r.get("净额") or 0),
                        "change_pct": float(r.get("行业-涨跌幅") or r.get("涨跌幅") or 0),
                        "inflow_yi": float(r.get("流入资金") or 0),
                        "outflow_yi": float(r.get("流出资金") or 0),
                        "source": source,
                    }
                )
            rows.sort(key=lambda x: -x["net_yi"])
            return rows
        except Exception as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"akshare {fn_name} failed: {last_err}")


def fetch_industry_flow_today_ak() -> list[dict]:
    return _ak_flow_table("stock_fund_flow_industry", "akshare_industry_today")


def fetch_concept_flow_today_ak() -> list[dict]:
    return _ak_flow_table("stock_fund_flow_concept", "akshare_concept_today")


def load_flow_from_mcp_cache(path: Path, source: str) -> list[dict] | None:
    """兼容 MCP get_fund_flow_rank 导出: {total,data:[{name,mainNetInflow,changePercent,...}]}"""
    raw = _load_json(path)
    if not raw:
        return None
    data = raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(data, list) or not data:
        return None
    rows = []
    for i, it in enumerate(data):
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        net = it.get("mainNetInflow")
        if net is None:
            continue
        net_f = float(net)
        rows.append(
            {
                "name": name,
                "net_yi": net_f / 1e8,  # 元 → 亿
                "net_yuan": net_f,
                "change_pct": float(it.get("changePercent") or 0),
                "code": it.get("code"),
                "rank": i + 1,
                "source": source,
            }
        )
    rows.sort(key=lambda x: -x["net_yi"])
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


def load_stock_industry_map() -> dict[str, dict]:
    """返回 {code: {industry, industry_l1, industry_l2, industry_l3, industry_path, ...}}"""
    raw = _load_json(MAP_PATH)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for k, v in raw.items():
        code = _bare(k)
        if isinstance(v, str) and v:
            out[code] = {
                "industry": v,
                "industry_l1": v,
                "industry_l2": "",
                "industry_l3": "",
                "industry_path": v,
            }
        elif isinstance(v, dict):
            ind = str(v.get("industry") or v.get("industry_l3") or v.get("industry_l1") or "")
            if not ind:
                continue
            out[code] = {
                "industry": ind,
                "industry_l1": str(v.get("industry_l1") or ""),
                "industry_l2": str(v.get("industry_l2") or ""),
                "industry_l3": str(v.get("industry_l3") or ""),
                "industry_path": str(v.get("industry_path") or ind),
                "name": str(v.get("name") or ""),
            }
    return out


def industry_aliases(meta: dict | str) -> list[str]:
    """用于与资金流板块名匹配的候选名（细→粗）。"""
    if isinstance(meta, str):
        return [meta] if meta else []
    names = []
    for k in ("industry", "industry_l3", "industry_l2", "industry_l1"):
        v = str(meta.get(k) or "").strip()
        if v and v not in names:
            names.append(v)
    # 去Ⅱ/Ⅲ 后缀再试一次（东财常叫「白酒」「银行」）
    extra = []
    for n in names:
        base = re.sub(r"[ⅡIIIⅢ123]+$", "", n).strip()
        if base and base not in names and base not in extra:
            extra.append(base)
    return names + extra


def resolve_industry(item: dict, ind_map: dict[str, dict]) -> str:
    for key in ("sector", "industry", "industry_name", "所属行业"):
        v = item.get(key)
        if v:
            return str(v).strip()
    code = _bare(item.get("symbol") or item.get("code") or "")
    meta = ind_map.get(code) or {}
    return str(meta.get("industry") or meta.get("industry_l1") or "")


def names_match(industry: str, sector_name: str) -> bool:
    """行业名匹配：优先精确；模糊匹配要求足够长，避免「电力」误伤「综合电力设备商」。"""
    a = (industry or "").strip()
    b = (sector_name or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    # 仅当较短方长度 >= 4 才做包含匹配，且必须是「短名是长名的完整子串」
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 4 and short in long:
        return True
    return False


def match_sector_row(industry: str, flow_rows: list[dict]) -> dict | None:
    if not industry:
        return None
    for r in flow_rows:
        if r["name"] == industry:
            return r
    for r in flow_rows:
        if names_match(industry, r["name"]):
            return r
    return None


def classify_sectors(
    today: list[dict],
    day3: list[dict] | None = None,
    top_allow: int = 20,
    bottom_deny: int = 30,
) -> dict:
    """根据今日 + 3 日资金流划分 allow / deny / neutral。

    注意：东财行业可达 400+ 个，不能把「略微流出」都拉黑，否则几乎全市场被拒。
    拒绝只针对：净流出排名靠后、或大额流出+下跌、或 1–3 日持续流出。
    """
    day3_map = {r["name"]: r for r in (day3 or [])}
    n = len(today)
    allow, deny, neutral = [], [], []
    deny_cut = max(1, n - bottom_deny)

    for i, r in enumerate(today):
        name = r["name"]
        net = float(r["net_yi"])
        chg = float(r.get("change_pct") or 0)
        r3 = day3_map.get(name)
        net3 = float(r3["net_yi"]) if r3 else None
        rank = i + 1

        hard_deny = False
        # 1) 流出榜尾（快轮动主信号）
        if rank > deny_cut and net < 0:
            hard_deny = True
        # 2) 大额流出 + 板块下跌
        if net <= -8.0 and chg <= -2.0:
            hard_deny = True
        # 3) 今日流出且近 3 日也明显流出（持续撤离）
        if net3 is not None and net <= -1.0 and net3 <= -5.0 and chg < 0:
            hard_deny = True
        # 4) 暴跌板块即使净额临界也拒绝
        if chg <= -6.0 and net < 0:
            hard_deny = True

        hard_allow = False
        if rank <= top_allow and net > 0 and chg > -3:
            hard_allow = True
        if net >= 3.0 and chg > -2:
            hard_allow = True
        if net3 is not None and net > 0 and net3 > 0 and chg > -3 and rank <= top_allow * 2:
            hard_allow = True

        # allow 优先于 deny（龙头流入板块不被误杀）
        tag = {
            "name": name,
            "net_yi": round(net, 2),
            "net3_yi": None if net3 is None else round(net3, 2),
            "change_pct": chg,
            "rank": rank,
        }
        if hard_allow:
            allow.append(tag)
        elif hard_deny:
            deny.append(tag)
        else:
            neutral.append(tag)

    return {
        "allow": allow,
        "deny": deny,
        "neutral": neutral,
        "n_today": n,
        "top_allow": top_allow,
        "bottom_deny": bottom_deny,
    }


def classify_concept_sectors(
    today: list[dict],
    day3: list[dict] | None = None,
    top_allow: int = 15,
    bottom_deny: int = 20,
) -> dict:
    """概念分类比行业更严：避免大半概念被拉黑。"""
    day3_map = {r["name"]: r for r in (day3 or [])}
    n = len(today)
    allow, deny, neutral = [], [], []
    deny_cut = max(1, n - bottom_deny)

    for i, r in enumerate(today):
        name = r["name"]
        net = float(r["net_yi"])
        chg = float(r.get("change_pct") or 0)
        r3 = day3_map.get(name)
        net3 = float(r3["net_yi"]) if r3 else None
        rank = i + 1

        hard_deny = False
        # 概念只抓「锋面撤离」：榜尾 或 极端单日流出（避免弱市把大部分概念拉黑）
        if rank > deny_cut and net < 0:
            hard_deny = True
        if net <= -20.0 and chg <= -3.0:
            hard_deny = True
        if (
            net3 is not None
            and rank > int(n * 0.75)
            and net <= -5.0
            and net3 <= -20.0
            and chg <= -3.0
        ):
            hard_deny = True

        hard_allow = False
        if rank <= top_allow and net > 0 and chg > -3:
            hard_allow = True
        if net >= 5.0 and chg > -2:
            hard_allow = True

        tag = {
            "name": name,
            "net_yi": round(net, 2),
            "net3_yi": None if net3 is None else round(net3, 2),
            "change_pct": chg,
            "rank": rank,
        }
        if hard_allow:
            allow.append(tag)
        elif hard_deny:
            deny.append(tag)
        else:
            neutral.append(tag)

    return {
        "allow": allow,
        "deny": deny,
        "neutral": neutral,
        "n_today": n,
        "top_allow": top_allow,
        "bottom_deny": bottom_deny,
    }


def load_stock_concept_map() -> dict[str, list[str]]:
    raw = _load_json(CONCEPT_MAP_PATH)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, v in raw.items():
        code = _bare(k)
        if isinstance(v, list):
            out[code] = [str(x) for x in v if x]
        elif isinstance(v, dict):
            cons = v.get("concepts") or []
            out[code] = [str(x) for x in cons if x]
    return out


def build_snapshot(
    today: list[dict] | None = None,
    day3: list[dict] | None = None,
    concept_today: list[dict] | None = None,
    concept_day3: list[dict] | None = None,
) -> dict:
    if today is None:
        today = load_flow_from_mcp_cache(DATA / "sector_flow_today.json", "mcp_industry_today")
        if not today:
            today = fetch_industry_flow_today_ak()
    if day3 is None:
        day3 = load_flow_from_mcp_cache(DATA / "sector_flow_3day.json", "mcp_industry_3day")

    if concept_today is None:
        concept_today = load_flow_from_mcp_cache(DATA / "concept_flow_today.json", "mcp_concept_today")
        if not concept_today:
            try:
                concept_today = fetch_concept_flow_today_ak()
            except Exception as e:
                print(f"  ⚠️ concept flow today fail: {e}", flush=True)
                concept_today = []
    if concept_day3 is None:
        concept_day3 = load_flow_from_mcp_cache(DATA / "concept_flow_3day.json", "mcp_concept_3day")

    classes = classify_sectors(today, day3)
    # 概念流先去掉标签/财报噪声名，再分类（概念池更小，阈值更严）
    def _clean_concept_rows(rows: list[dict] | None) -> list[dict]:
        if not rows:
            return []
        bad_kw = ("季报", "年报", "预减", "预增", "中特估", "中字头", "B股", "注册制", "次新股")
        out = []
        for r in rows:
            n = str(r.get("name") or "")
            if any(k in n for k in bad_kw):
                continue
            out.append(r)
        return out

    concept_today = _clean_concept_rows(concept_today)
    concept_day3 = _clean_concept_rows(concept_day3)
    concept_classes = (
        classify_concept_sectors(concept_today, concept_day3)
        if concept_today
        else {"allow": [], "deny": [], "neutral": [], "n_today": 0}
    )

    snap = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "classes": classes,
        "concept_classes": concept_classes,
        "today_top10": [
            {"name": r["name"], "net_yi": round(r["net_yi"], 2), "change_pct": r.get("change_pct")}
            for r in today[:10]
        ],
        "today_bottom10": [
            {"name": r["name"], "net_yi": round(r["net_yi"], 2), "change_pct": r.get("change_pct")}
            for r in today[-10:]
        ],
        "concept_top10": [
            {"name": r["name"], "net_yi": round(r["net_yi"], 2), "change_pct": r.get("change_pct")}
            for r in (concept_today or [])[:10]
        ],
        "has_3day": bool(day3),
        "has_concept": bool(concept_today),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return snap


def _status_from_names(
    names: list[str],
    allow_names: set[str],
    deny_names: set[str],
    allow_rows: list[dict],
    deny_rows: list[dict],
    fuzzy: bool = True,
) -> tuple[str, str, list[str]]:
    """返回 (status, reason, hit_names). status=allow|deny|neutral。
    概念层建议 fuzzy=False，避免「锂电池概念」误伤。
    """
    hits_allow, hits_deny = [], []
    for n in names:
        if not n:
            continue
        deny_hit = n in deny_names
        allow_hit = n in allow_names
        if fuzzy:
            deny_hit = deny_hit or any(names_match(n, d["name"]) for d in deny_rows)
            allow_hit = allow_hit or any(names_match(n, a["name"]) for a in allow_rows)
        if deny_hit:
            hits_deny.append(n)
        if allow_hit:
            hits_allow.append(n)
    if hits_deny:
        return "deny", f"命中流出:{','.join(hits_deny[:3])}", hits_deny
    if hits_allow:
        return "allow", f"命中流入:{','.join(hits_allow[:3])}", hits_allow
    return "neutral", "", []


def _is_denied_industry(industry: str, deny_names: set[str], deny_rows: list[dict]) -> tuple[bool, str]:
    if not industry:
        return False, ""
    if industry in deny_names:
        return True, f"板块流出拒绝:{industry}"
    for d in deny_rows:
        if names_match(industry, d["name"]):
            return True, f"板块流出拒绝:{d['name']}"
    # 仅当行业名本身就是科技类，且 deny 里有同关键词板块
    for kw in TECH_WEAK_KEYWORDS:
        if kw == industry or (len(kw) >= 3 and industry.startswith(kw)):
            for d in deny_rows:
                if kw in d["name"] and d.get("net_yi", 0) < 0:
                    return True, f"科技弱板块拒绝:{d['name']}(匹配{industry})"
    return False, ""


def _is_allowed_industry(industry: str, allow_names: set[str], allow_rows: list[dict]) -> bool:
    if not industry:
        return False
    if industry in allow_names:
        return True
    for a in allow_rows:
        if names_match(industry, a["name"]):
            return True
    return False


def decide_dual(
    ind_status: str,
    concept_status: str,
) -> tuple[bool, str, str]:
    """行业×概念决策。返回 (keep, final_status, reason)。

    规则（行业骨架优先）:
      行业 deny → 拒绝（行业大撤退，概念难救）
      行业 allow → 保留（主线行业不被噪声概念否决）
      行业 neutral + 概念 deny → 拒绝
      行业 neutral + 概念 allow → 保留（轮动锋面）
      双中性 → 拒绝
    """
    if ind_status == "deny":
        return False, "deny", "行业流出拒绝"
    if ind_status == "allow":
        if concept_status == "allow":
            return True, "allow", "行业+概念双流入"
        return True, "allow", "行业流入"
    # industry neutral
    if concept_status == "deny":
        return False, "deny", "概念流出拒绝"
    if concept_status == "allow":
        return True, "allow", "概念流入(轮动锋面)"
    return False, "neutral", "行业与概念均无资金锋面"


def apply_sector_rotation_gate(
    items: list[dict[str, Any]],
    snap: dict | None = None,
    mode: str = "dual",
    prefer_allow_ratio: float = 0.6,
) -> list[dict[str, Any]]:
    """
    硬门控：不修改 score。

    mode:
      - dual: 行业×概念联合硬删（对照）
      - soft_dual: 同 dual 判定，但 deny 只降分不删（生产默认）
      - deny_cold: 仅行业流出拒绝（旧逻辑）
      - allow_only: 只保留行业流入
      - hybrid: 行业 deny 后，提高 allow 占比
    """
    if not items:
        return items
    mode_in = mode
    soft_dual = mode == "soft_dual"
    if soft_dual:
        mode = "dual"  # 复用判定，deny 改为降分保留

    if snap is None:
        if SNAP.exists() and str(_load_json(SNAP) or {}).get("ts", "").startswith(time.strftime("%Y-%m-%d")):
            snap = _load_json(SNAP)
        else:
            snap = build_snapshot()

    classes = (snap or {}).get("classes") or {}
    allow_rows = classes.get("allow") or []
    deny_rows = classes.get("deny") or []
    allow_names = {x["name"] for x in allow_rows}
    deny_names = {x["name"] for x in deny_rows}

    c_classes = (snap or {}).get("concept_classes") or {}
    c_allow_rows = c_classes.get("allow") or []
    c_deny_rows = c_classes.get("deny") or []
    c_allow_names = {x["name"] for x in c_allow_rows}
    c_deny_names = {x["name"] for x in c_deny_rows}

    ind_map = load_stock_industry_map()
    concept_map = load_stock_concept_map()
    use_dual = mode == "dual" or bool(concept_map and (c_allow_rows or c_deny_rows))

    kept = []
    dropped = []
    soft_demoted = 0
    for it in items:
        code = _bare(it.get("symbol") or it.get("code") or "")
        meta = ind_map.get(code) or {}
        industry = resolve_industry(it, ind_map)
        aliases = industry_aliases(meta) if meta else ([industry] if industry else [])
        concepts = concept_map.get(code) or []

        ind_status, ind_reason, ind_hits = _status_from_names(
            aliases or [industry], allow_names, deny_names, allow_rows, deny_rows
        )
        # 兼容旧科技关键词兜底
        if ind_status == "neutral" and not industry and not meta and code.startswith(("300", "301", "688")):
            if any(kw in d["name"] for d in deny_rows for kw in ("半导体", "消费电子", "IT服务", "软件", "元件")):
                ind_status, ind_reason = "deny", "成长板且科技行业流出(无行业映射)"

        concept_status, concept_reason, concept_hits = "neutral", "", []
        if concepts and (c_allow_rows or c_deny_rows):
            concept_status, concept_reason, concept_hits = _status_from_names(
                concepts,
                c_allow_names,
                c_deny_names,
                c_allow_rows,
                c_deny_rows,
                fuzzy=False,
            )

        if mode == "dual":
            if concept_map and (c_allow_rows or c_deny_rows):
                keep, final_status, reason = decide_dual(ind_status, concept_status)
                # 细化原因，但不被次要层覆盖主因
                if ind_status == "deny":
                    reason = ind_reason or reason
                elif ind_status == "allow":
                    reason = "行业流入" + (f"；概念亦流入" if concept_status == "allow" else "")
                elif concept_status == "deny":
                    reason = concept_reason or reason
                elif concept_status == "allow":
                    reason = concept_reason or reason
            else:
                # 概念映射未就绪时降级为行业 deny_cold
                keep = ind_status != "deny"
                final_status = ind_status if ind_status != "neutral" else "neutral"
                reason = ind_reason if not keep else (ind_reason or "行业门控(概念未就绪)")
                if keep and ind_status == "neutral":
                    keep = True  # 概念未就绪时中性先放行，避免空池
                    final_status = "neutral"
        elif mode == "allow_only":
            keep = ind_status == "allow"
            final_status = ind_status
            reason = "不在流入行业" if not keep else (ind_reason or "行业流入")
        else:
            # deny_cold / hybrid 旧逻辑：只按行业 deny
            keep = ind_status != "deny"
            final_status = ind_status
            reason = ind_reason if not keep else (ind_reason or "pass")

        if not keep and not soft_dual:
            dropped.append((code, industry, reason))
            continue

        row = dict(it)
        row["sector_rotation"] = final_status
        row["sector_name_resolved"] = industry
        row["industry_status"] = ind_status
        row["concept_status"] = concept_status
        row["hit_industry"] = ind_hits[:5]
        row["hit_concepts"] = concept_hits[:5]
        row["concepts"] = concepts[:12]
        if meta:
            row["industry_path"] = meta.get("industry_path")
            row["industry_l1"] = meta.get("industry_l1")
        if not keep and soft_dual:
            base = float(row.get("score", 0) or 0)
            delta = -0.08
            row["score_raw_pre_sector"] = round(base, 4)
            row["sector_gate_delta"] = delta
            row["score"] = round(max(0.01, base + delta), 4)
            row["sector_gate"] = "soft_demote"
            row["sector_gate_reason"] = f"流出软降权:{reason}"
            soft_demoted += 1
        else:
            row["sector_gate"] = "pass"
            row["sector_gate_reason"] = reason
        kept.append(row)

    # soft_dual 不去裁剪 deny 票；hard dual 仍优先 allow
    if (not soft_dual) and mode in ("hybrid", "dual") and kept:
        allow_kept = [x for x in kept if x.get("sector_rotation") == "allow"]
        other = [x for x in kept if x.get("sector_rotation") != "allow"]
        n = len(kept)
        need_allow = int(n * prefer_allow_ratio)
        if allow_kept and len(allow_kept) >= max(1, need_allow // 2):
            max_other = max(0, n - min(len(allow_kept), max(need_allow, len(allow_kept))))
            if mode == "dual":
                max_other = min(len(other), max(0, int(n * (1 - prefer_allow_ratio))))
            kept = allow_kept + other[:max_other]

    kept.sort(key=lambda x: -float(x.get("score", 0) or 0))

    print(
        f"  sector_rotation_gate[{mode_in}]: keep={len(kept)} drop={len(dropped)} "
        f"soft_demote={soft_demoted} "
        f"ind_allow={len(allow_names)} ind_deny={len(deny_names)} "
        f"c_allow={len(c_allow_names)} c_deny={len(c_deny_names)} concepts_map={len(concept_map)}",
        flush=True,
    )
    if dropped[:8]:
        for code, ind, reason in dropped[:8]:
            print(f"    drop {code} [{ind}] {reason}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sector_rotation_gate_last.json").write_text(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "mode": mode_in,
                "kept": len(kept),
                "dropped": len(dropped),
                "soft_demoted": soft_demoted,
                "drop_samples": [
                    {"code": c, "industry": i, "reason": r} for c, i, r in dropped[:30]
                ],
                "allow_top": allow_rows[:10],
                "deny_top": deny_rows[:10],
                "concept_allow_top": c_allow_rows[:10],
                "concept_deny_top": c_deny_rows[:10],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return kept


if __name__ == "__main__":
    snap = build_snapshot()
    print("ind_allow", [x["name"] for x in snap["classes"]["allow"][:8]])
    print("ind_deny", [x["name"] for x in snap["classes"]["deny"][:8]])
    print("c_allow", [x["name"] for x in (snap.get("concept_classes") or {}).get("allow", [])[:8]])
    print("c_deny", [x["name"] for x in (snap.get("concept_classes") or {}).get("deny", [])[:8]])
    demo = [
        {"symbol": "300750", "score": 0.99, "name": "宁德时代"},
        {"symbol": "601988", "score": 0.55, "name": "中国银行"},
        {"symbol": "600900", "score": 0.60, "name": "长江电力"},
        {"symbol": "688981", "score": 0.95, "name": "中芯国际"},
    ]
    out = apply_sector_rotation_gate(demo, snap=snap, mode="dual")
    print(
        "kept",
        [
            (
                x["symbol"],
                x["score"],
                x.get("sector_rotation"),
                x.get("industry_status"),
                x.get("concept_status"),
                x.get("sector_gate_reason"),
            )
            for x in out
        ],
    )
