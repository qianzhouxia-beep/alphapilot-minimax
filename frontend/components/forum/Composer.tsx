// 发帖面板（示例版：不会真正发布到服务器，只加入当前页面的本地列表）
"use client";

import { useEffect, useRef, useState } from "react";
import {
  FORUM_LIMITS,
  type ForumPost,
  SECTIONS,
  STOCK_MAP,
  type SectionKey,
  checkContent,
  nowShanghaiIso,
} from "@/lib/forum-mock";

export function Composer({
  defaultSection,
  author,
  presetStock,
  onPublish,
  onClose,
}: {
  defaultSection: SectionKey;
  author: string;
  presetStock?: { name: string; code: string };
  onPublish: (post: ForumPost) => void;
  onClose: () => void;
}) {
  const [section, setSection] = useState<SectionKey>(defaultSection);
  const [title, setTitle] = useState(presetStock ? `关于 $${presetStock.name}$ ：` : "");
  const [body, setBody] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  const liveCheck = checkContent(`${title}\n${body}`);
  const tooLong = title.length > FORUM_LIMITS.titleMax || body.length > FORUM_LIMITS.bodyMax;
  const empty = !title.trim() || !body.trim();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (empty) return setErr("标题和正文都不能为空。");
    if (tooLong) return setErr("内容超出长度限制，请精简后再发布。");
    if (liveCheck.blocked) return setErr(liveCheck.blocked);
    const stocks = Array.from(`${title}${body}`.matchAll(/\$([^$]+)\$/g)).map((m) => m[1]);
    onPublish({
      id: `local-${Date.now()}`,
      section,
      title: title.trim(),
      body: body.trim(),
      author,
      time: nowShanghaiIso(),
      replies: 0,
      likes: 0,
      stocks: Array.from(new Set(stocks)).filter((n) => STOCK_MAP[n]).map((n) => ({ name: n, code: STOCK_MAP[n] })),
      // 注意：用户发帖永远不带 isOfficial / pinScope —— 官方帖与置顶只能由管理员在后台设置（见后端规格 §4.11），这里没有也不应该有对应入口
      isExample: true,
    });
    onClose();
  }

  const counter = (n: number, max: number) => (
    <span className={`text-[11px] tabular-nums ${n > max ? "text-status-danger" : "text-text-tertiary"}`}>
      {n}/{max}
    </span>
  );

  return (
    <section aria-labelledby="composer-title" className="rounded-2xl border border-purple-primary/30 bg-surface-card p-4 shadow-sm sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 id="composer-title" className="text-[16px] font-semibold text-text-primary">发表新帖</h2>
        <button type="button" onClick={onClose} className="cursor-pointer rounded-full px-3 py-1 text-[12px] text-text-secondary hover:bg-black/[0.05] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50">
          取消
        </button>
      </div>

      <form onSubmit={submit} className="mt-3 space-y-3" noValidate>
        <div>
          <label htmlFor="cmp-section" className="mb-1 block text-[12px] text-text-secondary">板块</label>
          <select
            id="cmp-section"
            value={section}
            onChange={(e) => setSection(e.target.value as SectionKey)}
            className="w-full rounded-xl border border-border-subtle bg-white px-3 py-2 text-[14px] text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 sm:w-auto"
          >
            {SECTIONS.map((s) => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between">
            <label htmlFor="cmp-title" className="text-[12px] text-text-secondary">标题</label>
            {counter(title.length, FORUM_LIMITS.titleMax)}
          </div>
          <input
            id="cmp-title"
            ref={titleRef}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={FORUM_LIMITS.titleMax + 20}
            placeholder="一句话说清你想讨论什么"
            className="w-full rounded-xl border border-border-subtle bg-white px-3 py-2.5 text-[15px] text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
          />
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between">
            <label htmlFor="cmp-body" className="text-[12px] text-text-secondary">正文</label>
            {counter(body.length, FORUM_LIMITS.bodyMax)}
          </div>
          <textarea
            id="cmp-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={6}
            aria-describedby="cmp-help"
            placeholder="可用 $股票名$ 引用股票，例如 $京能热力$。请讨论方法与观点，不要发布买卖指令。"
            className="w-full resize-y rounded-xl border border-border-subtle bg-white px-3 py-2.5 text-[14px] leading-relaxed text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
          />
        </div>

        <ul id="cmp-help" className="space-y-1 rounded-xl bg-purple-light/40 px-3 py-2.5 text-[12px] leading-relaxed text-text-secondary">
          <li>⚠️ 禁止留下微信 / QQ / 电话等联系方式及外部链接，含有此类内容的帖子无法发布。</li>
          <li>每日最多发 {FORUM_LIMITS.dailyPostLimit} 帖；账号注册满 {FORUM_LIMITS.minAccountAgeDays} 天后可发帖。</li>
          <li>先发后审：违规内容会被折叠或删除。内容仅供学习交流，不构成投资建议。</li>
        </ul>

        {(err || liveCheck.blocked) && (
          <p role="alert" className="rounded-xl border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-[13px] text-status-danger">
            {err ?? liveCheck.blocked}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[11px] text-text-tertiary">示例版本：提交后只会出现在本页面的本地列表里，不会真正发布。</p>
          <button
            type="submit"
            disabled={empty || tooLong || !!liveCheck.blocked}
            className="cursor-pointer rounded-full bg-purple-primary px-5 py-2 text-[13px] font-semibold text-on-primary transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            发布
          </button>
        </div>
      </form>
    </section>
  );
}
