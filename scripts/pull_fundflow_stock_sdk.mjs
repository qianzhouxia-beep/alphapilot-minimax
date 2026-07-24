#!/usr/bin/env node
/**
 * 用 stock-sdk（与 Cursor MCP stock-sdk 同源：东财资金流）批量拉全市场 ~120 日主力净流入。
 * 输出格式对齐 data/fund_flow_history.json: { "000001": { "YYYY-MM-DD": mainNet, ... }, ... }
 *
 * 用法:
 *   node scripts/pull_fundflow_stock_sdk.mjs [--out path] [--concurrency 8] [--limit N] [--codes path]
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { StockSDK } from "stock-sdk";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

function arg(name, def) {
  const i = process.argv.indexOf(name);
  if (i < 0) return def;
  return process.argv[i + 1] ?? def;
}
function has(name) {
  return process.argv.includes(name);
}

const OUT = path.resolve(arg("--out", path.join(ROOT, "data", "fund_flow_history.stock_sdk.json")));
const PROG = path.resolve(arg("--progress", path.join(ROOT, "data", "fund_flow_stock_sdk_progress.json")));
const CONCURRENCY = Math.max(1, parseInt(arg("--concurrency", "6"), 10) || 6);
const LIMIT = parseInt(arg("--limit", "0"), 10) || 0;
const VALIDATE_ONLY = has("--validate");
const SAMPLE = (arg("--sample", "000034,600519,000858") || "").split(",").map((s) => s.trim()).filter(Boolean);

function bare(code) {
  const s = String(code || "").toLowerCase().replace(/^(sh|sz|bj)/, "");
  return s.slice(-6);
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function mapPool(items, concurrency, fn) {
  let i = 0;
  const results = new Array(items.length);
  async function worker() {
    while (i < items.length) {
      const idx = i++;
      results[idx] = await fn(items[idx], idx);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => worker()));
  return results;
}

async function fetchOne(sdk, code) {
  const rows = await sdk.fundFlow.individual(code, { period: "daily" });
  const hist = {};
  for (const r of rows || []) {
    if (!r?.date) continue;
    const v = r.mainNetInflow;
    if (v == null || Number.isNaN(Number(v))) continue;
    hist[String(r.date).slice(0, 10)] = Number(v);
  }
  return hist;
}

async function validate(sdk) {
  const oldPath = path.join(ROOT, "data", "fund_flow_history.json");
  let old = {};
  if (fs.existsSync(oldPath)) {
    old = JSON.parse(fs.readFileSync(oldPath, "utf8"));
  }
  const report = [];
  for (const code of SAMPLE) {
    const hist = await fetchOne(sdk, code);
    const o = old[bare(code)] || old[code] || {};
    const dates = Object.keys(hist).sort();
    let agree = 0;
    let cmp = 0;
    const diffs = [];
    for (const d of dates.slice(-5)) {
      if (!(d in o)) continue;
      cmp++;
      const a = Number(hist[d]);
      const b = Number(o[d]);
      const ok = Math.abs(a - b) / Math.max(1, Math.abs(b)) < 0.05;
      if (ok) agree++;
      else diffs.push({ date: d, sdk: a, sina: b });
    }
    report.push({
      code: bare(code),
      sdk_days: dates.length,
      sdk_first: dates[0] || null,
      sdk_last: dates[dates.length - 1] || null,
      compare_n: cmp,
      agree_5pct: agree,
      diffs,
    });
  }
  const outp = path.join(ROOT, "output", "fund_flow_sdk_vs_sina.json");
  fs.mkdirSync(path.dirname(outp), { recursive: true });
  fs.writeFileSync(outp, JSON.stringify({ ts: new Date().toISOString(), report }, null, 2));
  console.log(JSON.stringify(report, null, 2));
  console.log("saved", outp);
}

async function main() {
  const sdk = new StockSDK();
  if (VALIDATE_ONLY) {
    await validate(sdk);
    return;
  }

  console.log("=== stock-sdk 全市场资金流拉取（MCP 同源）===");
  console.log({ OUT, CONCURRENCY, LIMIT });

  let codes = [];
  const codesFile = arg("--codes", "");
  if (codesFile && fs.existsSync(codesFile)) {
    codes = JSON.parse(fs.readFileSync(codesFile, "utf8")).map(bare);
  } else {
    const list = await sdk.codes.cn();
    codes = (list || []).map((x) => bare(x.code || x.symbol || x)).filter((c) => /^\d{6}$/.test(c));
  }
  codes = [...new Set(codes)].sort();
  if (LIMIT > 0) codes = codes.slice(0, LIMIT);
  console.log("codes", codes.length);

  let out = {};
  let done = new Set();
  if (fs.existsSync(PROG)) {
    try {
      const p = JSON.parse(fs.readFileSync(PROG, "utf8"));
      out = p.data || {};
      done = new Set(p.done || Object.keys(out));
      console.log("resume done", done.size);
    } catch {}
  }

  const todo = codes.filter((c) => !done.has(c));
  let ok = 0;
  let fail = 0;
  const t0 = Date.now();

  await mapPool(todo, CONCURRENCY, async (code, idx) => {
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const hist = await fetchOne(sdk, code);
        if (Object.keys(hist).length > 0) {
          out[code] = hist;
          ok++;
        } else {
          fail++;
        }
        break;
      } catch (e) {
        if (attempt === 2) {
          fail++;
          console.warn("fail", code, String(e?.message || e));
        } else {
          await sleep(400 * (attempt + 1));
        }
      }
    }
    if ((idx + 1) % 50 === 0 || idx + 1 === todo.length) {
      fs.mkdirSync(path.dirname(PROG), { recursive: true });
      fs.writeFileSync(
        PROG,
        JSON.stringify({ done: Object.keys(out), data: out, ok, fail, ts: new Date().toISOString() })
      );
      const sec = ((Date.now() - t0) / 1000).toFixed(0);
      console.log(`  ${idx + 1}/${todo.length} ok=${ok} fail=${fail} ${sec}s`);
    }
  });

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(out));
  const depths = Object.values(out).map((h) => Object.keys(h).length);
  const mean = depths.length ? depths.reduce((a, b) => a + b, 0) / depths.length : 0;
  console.log("saved", OUT);
  console.log({
    stocks: Object.keys(out).length,
    mean_depth: mean.toFixed(1),
    ok,
    fail,
    sec: ((Date.now() - t0) / 1000).toFixed(0),
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
