#!/usr/bin/env node
/** CommonJS batch pull using local stock-sdk (MCP 同源). */
const fs = require("fs");
const path = require("path");
const { StockSDK } = require("stock-sdk");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "data", "fund_flow_history.stock_sdk.json");
const PROG = path.join(ROOT, "data", "fund_flow_stock_sdk_progress.json");
const CODES_FILE = path.join(ROOT, "data", "a_share_codes.json");

const CONCURRENCY = parseInt(process.env.CONCURRENCY || "6", 10);
const LIMIT = parseInt(process.env.LIMIT || "0", 10);

function bare(code) {
  return String(code || "")
    .toLowerCase()
    .replace(/^(sh|sz|bj)/, "")
    .slice(-6);
}

async function mapPool(items, concurrency, fn) {
  let i = 0;
  const out = new Array(items.length);
  async function worker() {
    while (i < items.length) {
      const idx = i++;
      out[idx] = await fn(items[idx], idx);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => worker()));
  return out;
}

async function main() {
  const sdk = new StockSDK();
  let codes = [];
  if (fs.existsSync(CODES_FILE)) {
    const raw = JSON.parse(fs.readFileSync(CODES_FILE, "utf8"));
    const arr = Array.isArray(raw) ? raw : raw.data || raw.codes || [];
    codes = arr.map((x) => bare(typeof x === "string" ? x : x.code || x.symbol)).filter((c) => /^\d{6}$/.test(c));
  } else {
    const list = await sdk.codes.cn();
    codes = (list || []).map((x) => bare(x.code || x.symbol || x)).filter((c) => /^\d{6}$/.test(c));
  }
  codes = [...new Set(codes)].sort();
  if (LIMIT > 0) codes = codes.slice(0, LIMIT);
  console.log("codes", codes.length, "concurrency", CONCURRENCY);

  let data = {};
  let skipped = {};
  if (fs.existsSync(PROG)) {
    try {
      const p = JSON.parse(fs.readFileSync(PROG, "utf8"));
      data = p.data || {};
      skipped = p.skipped || {};
      console.log("resume", Object.keys(data).length, "skipped", Object.keys(skipped).length);
    } catch {}
  }
  const todo = codes.filter((c) => !data[c] && !skipped[c]);
  let ok = Object.keys(data).length;
  let fail = Object.keys(skipped).length;
  const t0 = Date.now();
  // 全局串行节流：即使多 worker 也共享最小间隔
  let nextSlot = 0;
  async function throttle() {
    const now = Date.now();
    const wait = Math.max(0, nextSlot - now);
    nextSlot = Math.max(nextSlot, now) + 200; // ~5 QPS
    if (wait) await new Promise((r) => setTimeout(r, wait));
  }

  await mapPool(todo, CONCURRENCY, async (code, idx) => {
    let got = false;
    for (let a = 0; a < 4; a++) {
      try {
        await throttle();
        const rows = await sdk.fundFlow.individual(code, { period: "daily" });
        const hist = {};
        for (const r of rows || []) {
          if (r?.date != null && r.mainNetInflow != null) hist[String(r.date).slice(0, 10)] = Number(r.mainNetInflow);
        }
        if (Object.keys(hist).length) {
          data[code] = hist;
          ok++;
          got = true;
        }
        break;
      } catch (e) {
        const msg = String(e.message || e);
        if (a === 3) {
          skipped[code] = msg.slice(0, 80);
          fail++;
          if (fail <= 40) console.warn("fail", code, msg);
        } else {
          await new Promise((r) => setTimeout(r, 1500 * (a + 1)));
        }
      }
    }
    if (!got && !skipped[code]) {
      skipped[code] = "empty";
      fail++;
    }
    if ((idx + 1) % 25 === 0 || idx + 1 === todo.length) {
      fs.writeFileSync(PROG, JSON.stringify({ data, skipped, ok, fail, ts: new Date().toISOString() }));
      console.log(`  ${idx + 1}/${todo.length} ok=${ok} fail=${fail} ${((Date.now() - t0) / 1000) | 0}s`);
    }
  });

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(data));
  const depths = Object.values(data).map((h) => Object.keys(h).length);
  const mean = depths.length ? depths.reduce((a, b) => a + b, 0) / depths.length : 0;
  console.log("saved", OUT, { stocks: Object.keys(data).length, mean_depth: mean.toFixed(1), ok, fail });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
