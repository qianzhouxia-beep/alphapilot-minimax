// 社区 — 帖子详情（示例数据版：点赞/收藏/举报/回复仅为界面演示，不会提交到服务器）
"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { HeaderBar } from "@/components/HeaderBar";
import { useAuth } from "@/lib/auth";
import { DISCLAIMER_FULL } from "@/lib/disclaimer";
import { LockedHint } from "@/components/LoginGate";
import { AuthorAvatar, AuthorName, PinTag, RichText, RulesBox, StockChip } from "@/components/forum/ForumBits";
import {
  FORUM_IS_MOCK,
  FORUM_LIMITS,
  SECTION_LABEL,
  checkContent,
  formatTime,
  getPost,
  listReplies,
  nowShanghaiIso,
  safeNickname,
  type ForumReply,
} from "@/lib/forum-mock";

const REPORT_REASONS = ["带单 / 喊单 / 荐股", "拉群 / 导流 / 联系方式", "广告 / 外链", "承诺收益 / 虚假信息", "人身攻击 / 骚扰", "其他"];

function ActionButton({
  pressed,
  onClick,
  label,
  count,
  children,
}: {
  pressed?: boolean;
  onClick: () => void;
  label: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-label={label}
      onClick={onClick}
      className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 ${
        pressed
          ? "border-purple-primary/30 bg-purple-light text-purple-primary"
          : "border-border-subtle bg-surface-card text-text-secondary hover:border-purple-primary/40 hover:text-purple-primary"
      }`}
    >
      {children}
      {count !== undefined && <span className="tabular-nums">{count}</span>}
    </button>
  );
}

export default function ForumPostPage() {
  const params = useParams<{ id: string }>();
  const id = String(params?.id ?? "");
  const post = getPost(id);
  const { session, openAuth } = useAuth();

  const [liked, setLiked] = useState(false);
  const [faved, setFaved] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [reason, setReason] = useState<string>(REPORT_REASONS[0]);
  const [reported, setReported] = useState(false);
  const [extraReplies, setExtraReplies] = useState<ForumReply[]>([]);
  const [replyText, setReplyText] = useState("");
  const [replyErr, setReplyErr] = useState<string | null>(null);
  const [replyLikes, setReplyLikes] = useState<Record<string, boolean>>({});

  const need = (fn: () => void) => () => {
    if (!session) return openAuth("login", `/cn/forum/${id}`);
    fn();
  };

  if (!post) {
    return (
      <main className="mx-auto min-h-screen max-w-[1200px] px-4 py-3 sm:px-6 sm:py-5 lg:px-8 lg:py-6">
        <HeaderBar market="cn" />
        <div className="rounded-2xl border border-dashed border-border-medium px-4 py-14 text-center">
          <p className="text-[16px] font-semibold text-text-primary">没有找到这篇帖子</p>
          <p className="mt-1 text-[13px] text-text-secondary">它可能已被删除，或链接有误。</p>
          <Link href="/cn/forum" className="mt-4 inline-block rounded-full bg-purple-primary px-5 py-2 text-[13px] font-semibold text-on-primary">
            返回社区
          </Link>
        </div>
      </main>
    );
  }

  const replies = [...listReplies(post.id), ...extraReplies];

  function submitReply(e: React.FormEvent) {
    e.preventDefault();
    const text = replyText.trim();
    if (!text) return setReplyErr("回复内容不能为空。");
    if (text.length > FORUM_LIMITS.replyMax) return setReplyErr(`回复最多 ${FORUM_LIMITS.replyMax} 字。`);
    const c = checkContent(text);
    if (c.blocked) return setReplyErr(c.blocked);
    setExtraReplies((r) => [
      ...r,
      { id: `local-${Date.now()}`, postId: post!.id, author: safeNickname(session?.user.full_name), time: nowShanghaiIso(), body: text, likes: 0 },
    ]);
    setReplyText("");
    setReplyErr(null);
  }

  return (
    <main className="mx-auto min-h-screen max-w-[1200px] px-4 py-3 sm:px-6 sm:py-5 lg:px-8 lg:py-6">
      <HeaderBar market="cn" />

      <nav aria-label="面包屑" className="mb-3 text-[13px] text-text-secondary">
        <Link href="/cn/forum" className="hover:text-purple-primary">← 社区</Link>
        <span aria-hidden className="mx-2 text-text-disabled">/</span>
        <span>{SECTION_LABEL[post.section]}</span>
      </nav>

      {FORUM_IS_MOCK && (
        <p role="note" className="mb-4 rounded-xl border border-dashed border-border-medium bg-surface-card px-4 py-2.5 text-[12px] leading-relaxed text-text-secondary">
          <strong className="font-semibold text-text-primary">示例数据：</strong>本帖与回复均为演示用的虚构内容；点赞、收藏、举报、回复不会提交到服务器。
        </p>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-4">
          <article className={`rounded-2xl border p-4 shadow-sm sm:p-6 ${post.isOfficial ? "border-purple-primary/20 bg-purple-light/30" : "border-border-subtle bg-surface-card"}`}>
            <div className="flex flex-wrap items-center gap-2 text-[12px]">
              {post.pinScope && <PinTag scope={post.pinScope} />}
              <span className="rounded-full bg-black/[0.05] px-2 py-0.5 text-text-secondary">{SECTION_LABEL[post.section]}</span>
            </div>
            <h1 className="mt-2 break-words text-[22px] font-semibold leading-snug tracking-tight text-text-primary sm:text-[26px]">
              {post.title.replace(/\$([^$]+)\$/g, "$1")}
            </h1>
            <div className="mt-3 flex items-center gap-3 text-[13px] text-text-tertiary">
              <AuthorAvatar name={post.author} official={post.isOfficial} size={36} />
              <div className="min-w-0">
                <div className="flex min-w-0 flex-wrap items-center gap-2 font-medium text-text-primary">
                  {post.isOfficial ? <AuthorName name={post.author} official /> : <span className="truncate">{post.author}</span>}
                </div>
                <time dateTime={post.time}>{formatTime(post.time)}</time>
              </div>
            </div>

            <RichText text={post.body} className="mt-4 text-[15px] leading-[1.8] text-text-primary" />

            {post.stocks.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border-subtle pt-3">
                <span className="text-[12px] text-text-tertiary">相关股票</span>
                {post.stocks.map((s) => (
                  <StockChip key={s.code} {...s} />
                ))}
              </div>
            )}

            <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border-subtle pt-4">
              <ActionButton pressed={liked} label={liked ? "取消点赞" : "点赞"} onClick={need(() => setLiked((v) => !v))} count={post.likes + (liked ? 1 : 0)}>
                <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M7 11v9H4v-9h3zm0 0 4-7a2 2 0 0 1 2 2v3h5.4a2 2 0 0 1 2 2.3l-1 6A2 2 0 0 1 17.4 19H7" />
                </svg>
                赞
              </ActionButton>
              <ActionButton pressed={faved} label={faved ? "取消收藏" : "收藏"} onClick={need(() => setFaved((v) => !v))}>
                <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill={faved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 3h12v18l-6-4-6 4V3z" />
                </svg>
                {faved ? "已收藏" : "收藏"}
              </ActionButton>
              <button
                type="button"
                aria-expanded={reportOpen}
                aria-controls="report-panel"
                onClick={need(() => setReportOpen((v) => !v))}
                className="ml-auto inline-flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] text-text-tertiary transition-colors hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
              >
                <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 21V4m0 0h11l-2 4 2 4H5" />
                </svg>
                举报
              </button>
            </div>

            {reportOpen && (
              <div id="report-panel" className="mt-3 rounded-xl border border-border-subtle bg-bg-primary/60 p-4">
                {reported ? (
                  <p role="status" className="text-[13px] text-text-secondary">
                    已收到你的举报（示例，未提交到服务器）。正式版中，累计 {FORUM_LIMITS.reportFoldThreshold} 次举报会自动折叠并进入人工审核。
                  </p>
                ) : (
                  <fieldset>
                    <legend className="text-[13px] font-medium text-text-primary">举报原因</legend>
                    <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                      {REPORT_REASONS.map((r) => (
                        <label key={r} className="flex cursor-pointer items-center gap-2 text-[13px] text-text-secondary">
                          <input type="radio" name="report-reason" checked={reason === r} onChange={() => setReason(r)} className="accent-[#7C5CFC]" />
                          {r}
                        </label>
                      ))}
                    </div>
                    <div className="mt-3 flex gap-2">
                      <button type="button" onClick={() => setReported(true)} className="cursor-pointer rounded-full bg-purple-primary px-4 py-1.5 text-[13px] font-semibold text-on-primary hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50">
                        提交举报
                      </button>
                      <button type="button" onClick={() => setReportOpen(false)} className="cursor-pointer rounded-full px-4 py-1.5 text-[13px] text-text-secondary hover:bg-black/[0.05]">
                        取消
                      </button>
                    </div>
                  </fieldset>
                )}
              </div>
            )}
          </article>

          <section aria-labelledby="replies-title" className="rounded-2xl border border-border-subtle bg-surface-card p-4 shadow-sm sm:p-6">
            <h2 id="replies-title" className="text-[16px] font-semibold text-text-primary">
              回复 <span className="text-text-tertiary">{replies.length}</span>
            </h2>

            {replies.length === 0 ? (
              <p className="mt-3 rounded-xl border border-dashed border-border-medium px-4 py-6 text-center text-[13px] text-text-secondary">还没有回复，来说两句吧。</p>
            ) : (
              <ol className="mt-3 divide-y divide-border-subtle">
                {replies.map((r, i) => (
                  <li key={r.id} className="flex gap-3 py-4 first:pt-1">
                    <AuthorAvatar name={r.author} official={r.isOfficial} size={32} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-2 text-[13px]">
                        {r.isOfficial ? <AuthorName name={r.author} official /> : <span className="font-medium text-text-primary">{r.author}</span>}
                        <time dateTime={r.time} className="text-[12px] text-text-tertiary">{formatTime(r.time)}</time>
                        <span className="ml-auto text-[12px] text-text-disabled">#{i + 1}</span>
                      </div>
                      <RichText text={r.body} className="mt-1 text-[14px] leading-relaxed text-text-primary" />
                      <button
                        type="button"
                        aria-pressed={!!replyLikes[r.id]}
                        onClick={need(() => setReplyLikes((m) => ({ ...m, [r.id]: !m[r.id] })))}
                        className={`mt-1.5 inline-flex cursor-pointer items-center gap-1 rounded-full px-2 py-0.5 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 ${
                          replyLikes[r.id] ? "text-purple-primary" : "text-text-tertiary hover:text-purple-primary"
                        }`}
                      >
                        赞 <span className="tabular-nums">{r.likes + (replyLikes[r.id] ? 1 : 0)}</span>
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
            )}

            <div className="mt-4 border-t border-border-subtle pt-4">
              {session ? (
                <form onSubmit={submitReply} noValidate>
                  <label htmlFor="reply-body" className="mb-1 flex items-center justify-between text-[12px] text-text-secondary">
                    <span>写回复</span>
                    <span className={`tabular-nums ${replyText.length > FORUM_LIMITS.replyMax ? "text-status-danger" : "text-text-tertiary"}`}>
                      {replyText.length}/{FORUM_LIMITS.replyMax}
                    </span>
                  </label>
                  <textarea
                    id="reply-body"
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    rows={3}
                    placeholder="友善、理性地讨论；不要留联系方式或外链。"
                    className="w-full resize-y rounded-xl border border-border-subtle bg-white px-3 py-2.5 text-[14px] text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
                  />
                  {replyErr && <p role="alert" className="mt-2 text-[13px] text-status-danger">{replyErr}</p>}
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <p className="text-[11px] text-text-tertiary">示例版本：回复仅在本页显示。</p>
                    <button type="submit" className="cursor-pointer rounded-full bg-purple-primary px-5 py-2 text-[13px] font-semibold text-on-primary hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50">
                      回复
                    </button>
                  </div>
                </form>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-purple-light/40 px-4 py-3">
                  <p className="text-[13px] text-text-secondary">登录后可以回复、点赞和收藏。</p>
                  <LockedHint label="登录后回复" />
                </div>
              )}
            </div>
          </section>
        </div>

        <div className="space-y-4 lg:sticky lg:top-24">
          <RulesBox />
        </div>
      </div>

      <footer className="mx-auto mt-10 max-w-3xl pb-6 text-center text-[11px] leading-relaxed text-text-tertiary">
        {DISCLAIMER_FULL}
      </footer>
    </main>
  );
}
