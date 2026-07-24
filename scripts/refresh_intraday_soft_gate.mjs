#!/usr/bin/env node
/**
 * 刷新盘中软门控快照：资金流排名(today/5day) + 可选行情。
 * 写入 data/intraday_soft_gate.json 供 soft_intraday_gate.py 使用。
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { StockSDK } from "stock-sdk";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "data", "intraday_soft_gate.json");

function bare(code) {
  return String(code || "")
    .toLowerCase()
    .replace(/^(sh|sz|bj)/, "")
    .slice(-6);
}

function toMap(rankList) {
  const m = {};
  (rankList || []).forEach((item, i) => {
    const code = bare(item.code || item.symbol);
    if (!code) return;
    m[code] = {
      rank: i + 1,
      name: item.name,
      mainNetInflow: item.mainNetInflow,
      mainNetInflowPercent: item.mainNetInflowPercent,
      changePercent: item.changePercent,
      price: item.price,
    };
  });
  return m;
}

async function main() {
  const sdk = new StockSDK();
  console.log("refresh intraday soft gate...");
  const [today, d5] = await Promise.all([
    sdk.fundFlow.rank({ indicator: "today" }),
    sdk.fundFlow.rank({ indicator: "5day" }),
  ]);
  const rank_today = toMap(today);
  const rank_5day = toMap(d5);

  // 取 today 排名前 200 的行情（轻量）
  const topCodes = Object.entries(rank_today)
    .sort((a, b) => a[1].rank - b[1].rank)
    .slice(0, 200)
    .map(([c]) => (c.startsWith("6") ? `sh${c}` : `sz${c}`));

  let quotes = {};
  try {
    const qs = await sdk.quotes.cn(topCodes);
    for (const q of qs || []) {
      const code = bare(q.code || q.symbol);
      quotes[code] = {
        price: q.price ?? q.last ?? q.close,
        changePercent: q.changePercent ?? q.change_pct,
        turnover: q.turnover ?? q.turnoverRate,
        volume: q.volume,
        name: q.name,
      };
    }
  } catch (e) {
    console.warn("quotes failed:", e?.message || e);
  }

  const payload = {
    ts: new Date().toISOString(),
    source: "stock-sdk",
    n_rank_today: Object.keys(rank_today).length,
    n_rank_5day: Object.keys(rank_5day).length,
    n_quotes: Object.keys(quotes).length,
    rank_today,
    rank_5day,
    quotes,
  };
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(payload));
  console.log("saved", OUT, {
    n_rank_today: payload.n_rank_today,
    n_rank_5day: payload.n_rank_5day,
    n_quotes: payload.n_quotes,
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
