// A 股交易时段状态（按 Asia/Shanghai 计算，不依赖浏览器本地时区）
// 注意：仅按"周一至周五 + 常规时段"判断，未接入法定节假日日历；节假日会显示为常规工作日状态。
"use client";

import { useEffect, useState } from "react";

export type MarketPhase = "pre" | "open" | "lunch" | "closed" | "weekend";

export type MarketStatus = {
  phase: MarketPhase;
  /** 短标签，如「A 股交易中」 */
  label: string;
  /** 语义色调：live=交易中(绿点)、wait=等待(琥珀点)、idle=已收盘(灰点) */
  tone: "live" | "wait" | "idle";
  /** 上海时间 HH:mm */
  clock: string;
  /** 上海日期，如「10月2日 周五」 */
  date: string;
};

function shanghaiDate(now: Date) {
  const p = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "numeric",
    day: "numeric",
    weekday: "short",
  }).formatToParts(now);
  const g = (t: string) => p.find((x) => x.type === t)?.value ?? "";
  return `${g("month")}月${g("day")}日 ${g("weekday")}`;
}

function shanghaiParts(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const wd = get("weekday");
  const hh = Number(get("hour"));
  const mm = Number(get("minute"));
  return { wd, hh, mm, clock: `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}` };
}

export function getMarketStatus(now = new Date()): MarketStatus {
  const { wd, hh, mm, clock } = shanghaiParts(now);
  const date = shanghaiDate(now);
  const mins = hh * 60 + mm;
  if (wd === "Sat" || wd === "Sun") {
    return { phase: "weekend", label: "A 股休市", tone: "idle", clock, date };
  }
  if (mins >= 555 && mins < 570) return { phase: "pre", label: "集合竞价", tone: "wait", clock, date };
  if ((mins >= 570 && mins < 690) || (mins >= 780 && mins < 900)) {
    return { phase: "open", label: "A 股交易中", tone: "live", clock, date };
  }
  if (mins >= 690 && mins < 780) return { phase: "lunch", label: "午间休市", tone: "wait", clock, date };
  return { phase: "closed", label: "A 股已收盘", tone: "idle", clock, date };
}

/** 客户端挂载后才返回真实状态（静态导出页面避免 hydration 不一致），每 30 秒刷新。 */
export function useMarketStatus(): MarketStatus | null {
  const [s, setS] = useState<MarketStatus | null>(null);
  useEffect(() => {
    const tick = () => setS(getMarketStatus());
    tick();
    const id = window.setInterval(tick, 30000);
    return () => window.clearInterval(id);
  }, []);
  return s;
}

export const MARKET_STATUS_NOTE = "按北京时间常规交易时段判断，未计入法定节假日休市。";
