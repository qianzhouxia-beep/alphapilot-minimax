// 发帖面板：调用 POST /posts；被拒绝时在表单内显示中文原因（昵称含保留词时可直接改昵称）
"use client";

import { useEffect, useRef, useState } from "react";
import { useReloginPrompt } from "@/lib/forum-hooks";
import {
  type CreatePostResponse,
  FORUM_LIMITS,
  type Quota,
  SECTIONS,
  type SectionKey,
  contentHint,
  createPost,
  describeError,
  setNickname,
} from "@/lib/forum-api";

export function Composer({
  defaultSection,
  quota,
  presetStock,
  onPublished,
  onClose,
}: {
  defaultSection: SectionKey;
  quota: Quota | null;
  presetStock?: { name: string; code: string };
  onPublished: (r: CreatePostResponse) => void;
  onClose: () => void;
}) {
  const relogin = useReloginPrompt();
  const [section, setSection] = useState<SectionKey>(defaultSection);
  const [title, setTitle] = useState(presetStock ? `关于 $${presetStock.name}$ ：` : "");
  const [body, setBody] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [needNick, setNeedNick] = useState(false);
  const [nick, setNick] = useState("");
  const [nickBusy, setNickBusy] = useState(false);
  const [nickOk, setNickOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  const hint = contentHint(`${title}\n${body}`);
  const tooLong = title.length > FORUM_LIMITS.titleMax || body.length > FORUM_LIMITS.bodyMax;
  const empty = !title.trim() || !body.trim();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (empty) return setErr("标题和正文都不能为空。");
    if (tooLong) return setErr("内容超出长度限制，请精简后再发布。");
    setErr(null);
    setBusy(true);
    try {
      const r = await createPost({ section, title: title.trim(), body: body.trim() });
      onPublished(r);
      onClose();
    } catch (ex) {
      const d = describeError(ex);
      setErr(d.message);
      if (d.action === "nickname") setNeedNick(true);
      if (d.action === "login") relogin("/cn/forum/");
    } finally {
      setBusy(false);
    }
  }

  async function saveNick() {
    const v = nick.trim();
    if (!v || nickBusy) return;
    setNickBusy(true);
    setNickOk(null);
    try {
      const r = await setNickname(v);
      setNickOk(`昵称已改为「${r.nickname}」，可以再次点击发布。`);
      setErr(null);
      setNeedNick(false);
    } catch (ex) {
      setErr(describeError(ex).message);
    } finally {
      setNickBusy(false);
    }
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
          <li>每日最多发 {quota?.posts_limit ?? FORUM_LIMITS.dailyPostLimit} 帖；账号注册满 {FORUM_LIMITS.minAccountAgeDays} 天后可发帖。</li>
          <li>先发后审：违规内容会被折叠或删除。内容仅供学习交流，不构成投资建议。</li>
        </ul>

        {hint && !err && (
          <p className="rounded-xl border border-border-medium bg-black/[0.03] px-3 py-2 text-[12px] text-text-secondary">{hint}</p>
        )}

        {err && (
          <p role="alert" className="rounded-xl border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-[13px] text-status-danger">
            {err}
          </p>
        )}

        {needNick && (
          <div className="rounded-xl border border-purple-primary/30 bg-purple-light/40 p-3">
            <label htmlFor="cmp-nick" className="block text-[12px] text-text-secondary">
              修改社区昵称{quota?.nickname ? `（当前：${quota.nickname}）` : ""}
            </label>
            <div className="mt-1.5 flex gap-2">
              <input
                id="cmp-nick"
                value={nick}
                onChange={(e) => setNick(e.target.value)}
                maxLength={20}
                placeholder="输入新昵称，不含官方、站务等词"
                className="min-w-0 flex-1 rounded-xl border border-border-subtle bg-white px-3 py-2 text-[14px] text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
              />
              <button
                type="button"
                onClick={saveNick}
                disabled={!nick.trim() || nickBusy}
                className="shrink-0 cursor-pointer rounded-full bg-purple-primary px-4 py-2 text-[13px] font-semibold text-on-primary hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {nickBusy ? "保存中" : "保存昵称"}
              </button>
            </div>
          </div>
        )}
        {nickOk && <p role="status" className="text-[12px] text-text-secondary">{nickOk}</p>}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[11px] text-text-tertiary">
            {quota ? `发布昵称：${quota.nickname}，今日还可发 ${quota.remaining_today} 帖` : "发布后会立即显示，违规内容会被折叠或删除"}
          </p>
          <button
            type="submit"
            disabled={empty || tooLong || busy}
            className="cursor-pointer rounded-full bg-purple-primary px-5 py-2 text-[13px] font-semibold text-on-primary transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "发布中" : "发布"}
          </button>
        </div>
      </form>
    </section>
  );
}
