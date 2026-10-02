// 社区通用小组件：头像 / 股票标签 / 带 $股票$ 的富文本 / 帖子卡片 / 帖子列表 / 社区规则
// 数据来自 lib/forum-api.ts（真实接口）。
"use client";

import Link from "next/link";
import { useState } from "react";
import {
  type ForumAuthor,
  type ForumPost,
  type ForumStock,
  OFFICIAL_NAME,
  type PinScope,
  SECTION_LABEL,
  formatTime,
  postHref,
  stripMarks,
} from "@/lib/forum-api";

export function Avatar({ initial, size = 32 }: { initial: string; size?: number }) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size, fontSize: Math.round(size * 0.42) }}
      className="inline-flex shrink-0 items-center justify-center rounded-full bg-purple-light font-semibold text-purple-primary"
    >
      {initial}
    </span>
  );
}

/** 官方头像：品牌紫底 + 白色三角 logo（与站点 logo 同形） */
export function OfficialAvatar({ size = 32 }: { size?: number }) {
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className="inline-flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#7C5CFC] to-[#A78BFA]"
    >
      <svg viewBox="0 0 32 32" style={{ width: size * 0.56, height: size * 0.56 }} fill="none">
        <path d="M16 4 L28 27 L4 27 Z" fill="#fff" fillOpacity="0.95" />
        <path d="M16 14 L21 23 L11 23 Z" fill="#7C5CFC" />
      </svg>
    </span>
  );
}

/** 头像：官方帖/官方回复用品牌头像，其余用昵称首字 */
export function AuthorAvatar({ author, size = 32 }: { author: ForumAuthor; size?: number }) {
  return author.is_official ? <OfficialAvatar size={size} /> : <Avatar initial={author.avatar_initial || author.nickname.slice(0, 1)} size={size} />;
}

/** 「AlphaPilot 官方」徽标 */
export function OfficialBadge({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border border-purple-primary/30 bg-white px-2 py-0.5 text-[11px] font-medium text-purple-primary ${className}`}
    >
      <svg aria-hidden viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="m8.5 12 2.5 2.5 4.5-5" />
      </svg>
      {OFFICIAL_NAME}
    </span>
  );
}

/** 作者名：官方帖显示徽标（徽标自带站点名），普通用户显示昵称 */
export function AuthorName({ author }: { author: ForumAuthor }) {
  return author.is_official ? <OfficialBadge /> : <span className="max-w-[160px] truncate text-text-secondary">{author.nickname}</span>;
}

/** 置顶标签：global=全站置顶，section=本版置顶 */
export function PinTag({ scope }: { scope: PinScope }) {
  if (scope === "none") return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-purple-primary px-2 py-0.5 text-[11px] font-medium text-white">
      置顶
      <span className="font-normal text-white/80">· {scope === "global" ? "全站" : "本版"}</span>
    </span>
  );
}

export function StockChip({ name, code }: { name: string; code: string }) {
  return (
    <Link
      href={`/cn/stock?symbol=${code}`}
      onClick={(e) => e.stopPropagation()}
      className="inline-flex items-center gap-1 rounded-full border border-purple-primary/25 bg-purple-light/60 px-2 py-0.5 text-[12px] text-purple-primary transition-colors hover:bg-purple-light focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
    >
      <span aria-hidden>$</span>
      {name}
      {name !== code && <span className="font-mono text-[11px] text-purple-primary/70">{code}</span>}
    </Link>
  );
}

/** 把正文里的 $股票名$ 渲染成链接，其余原样输出（保留换行）；不认识的名称按普通文本显示 */
export function RichText({ text, stocks = [], className = "" }: { text: string; stocks?: ForumStock[]; className?: string }) {
  const codeOf = (n: string) => stocks.find((s) => s.name === n || s.code === n || s.symbol === n)?.code;
  const parts = text.split(/(\$[^$]+\$)/g);
  return (
    <p className={`whitespace-pre-wrap break-words ${className}`}>
      {parts.map((part, i) => {
        const m = part.match(/^\$([^$]+)\$$/);
        if (!m) return <span key={i}>{part}</span>;
        const code = codeOf(m[1]);
        return code ? (
          <span key={i} className="mx-0.5 inline-block align-baseline">
            <StockChip name={m[1]} code={code} />
          </span>
        ) : (
          <span key={i}>{m[1]}</span>
        );
      })}
    </p>
  );
}

const Icon = {
  reply: (
    <svg aria-hidden viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
    </svg>
  ),
  like: (
    <svg aria-hidden viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 11v9H4v-9h3zm0 0 4-7a2 2 0 0 1 2 2v3h5.4a2 2 0 0 1 2 2.3l-1 6A2 2 0 0 1 17.4 19H7" />
    </svg>
  ),
};

export function PostCard({ post, showSection = true }: { post: ForumPost; showSection?: boolean }) {
  const folded = post.status === "folded";
  return (
    <li>
      <article
        className={`card-lift relative rounded-2xl border p-4 shadow-sm transition-colors hover:border-purple-primary/30 sm:p-5 ${
          post.is_official ? "border-purple-primary/20 bg-purple-light/30" : "border-border-subtle bg-surface-card"
        }`}
      >
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <PinTag scope={post.pin_scope} />
          {showSection && (
            <span className="rounded-full bg-black/[0.05] px-2 py-0.5 text-text-secondary">{post.section_label || SECTION_LABEL[post.section]}</span>
          )}
          {folded && <span className="rounded-full bg-black/[0.05] px-2 py-0.5 text-text-tertiary">已折叠</span>}
        </div>

        <h3 className="mt-2 text-[16px] font-semibold leading-snug text-text-primary sm:text-[17px]">
          {/* 整卡可点：标题链接用 ::after 撑满卡片，内部的股票标签用 relative z-10 保持可点 */}
          <Link
            href={postHref(post.id)}
            className="break-words after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:rounded-2xl focus-visible:after:ring-2 focus-visible:after:ring-purple-primary/50"
          >
            {stripMarks(post.title)}
          </Link>
        </h3>
        <p className="mt-1.5 line-clamp-2 break-words text-[13px] leading-relaxed text-text-secondary">
          {folded ? post.fold_reason_label || "该帖已被折叠，点开可查看原文。" : post.excerpt ? stripMarks(post.excerpt) : ""}
        </p>

        {post.stocks.length > 0 && (
          <div className="relative z-10 mt-3 flex flex-wrap gap-1.5">
            {post.stocks.map((s) => (
              <StockChip key={s.code} name={s.name} code={s.code} />
            ))}
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12px] text-text-tertiary">
          <span className="inline-flex min-w-0 items-center gap-2">
            <AuthorAvatar author={post.author} size={24} />
            <AuthorName author={post.author} />
          </span>
          <time dateTime={post.created_at}>{formatTime(post.created_at)}</time>
          <span className="ml-auto inline-flex items-center gap-3">
            <span className="inline-flex items-center gap-1" aria-label={`${post.reply_count} 条回复`}>
              {Icon.reply}
              {post.reply_count}
            </span>
            <span className="inline-flex items-center gap-1" aria-label={`${post.like_count} 个赞`}>
              {Icon.like}
              {post.like_count}
            </span>
          </span>
        </div>
      </article>
    </li>
  );
}

/** 置顶区：紧凑的单行列表（淡紫底），超过 3 条时默认只显示前 3 条，可展开 */
export function PinnedBlock({ posts, showSection = false }: { posts: ForumPost[]; showSection?: boolean }) {
  const [open, setOpen] = useState(false);
  if (posts.length === 0) return null;
  const LIMIT = 3;
  const shown = open ? posts : posts.slice(0, LIMIT);
  return (
    <section aria-label="置顶帖" className="rounded-2xl border border-purple-primary/20 bg-purple-light/40 p-1.5 sm:p-2">
      <ul className="divide-y divide-purple-primary/10">
        {shown.map((p) => (
          <li key={p.id} className="relative flex items-start gap-2 rounded-xl px-2.5 py-2.5 transition-colors hover:bg-white/60 sm:items-center sm:gap-3 sm:px-3">
            <span className="mt-0.5 shrink-0 sm:mt-0"><PinTag scope={p.pin_scope} /></span>
            <span className="min-w-0 flex-1">
              <Link
                href={postHref(p.id)}
                className="block break-words text-[14px] font-medium leading-snug text-text-primary after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-purple-primary/50 sm:truncate"
              >
                {p.title}
              </Link>
              <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 sm:hidden">
                {p.is_official && <OfficialBadge />}
              </span>
            </span>
            <span className="hidden shrink-0 items-center gap-2 sm:inline-flex">
              {showSection && <span className="rounded-full bg-black/[0.05] px-2 py-0.5 text-[11px] text-text-secondary">{SECTION_LABEL[p.section]}</span>}
              {p.is_official && <OfficialBadge />}
            </span>
          </li>
        ))}
      </ul>
      {posts.length > LIMIT && (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className="mt-1 w-full cursor-pointer rounded-xl px-3 py-1.5 text-center text-[12px] text-purple-primary hover:bg-white/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
        >
          {open ? "收起置顶" : `展开全部 ${posts.length} 条置顶`}
        </button>
      )}
    </section>
  );
}

export function PostList({
  posts,
  emptyTitle = "这里还没有讨论",
  emptyHint = "来发第一帖吧。",
  showSection = true,
}: {
  posts: ForumPost[];
  emptyTitle?: string;
  emptyHint?: string;
  showSection?: boolean;
}) {
  if (posts.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border-medium px-4 py-10 text-center">
        <p className="text-[14px] font-medium text-text-primary">{emptyTitle}</p>
        <p className="mt-1 text-[13px] text-text-secondary">{emptyHint}</p>
      </div>
    );
  }
  return (
    <ul className="grid gap-3">
      {posts.map((p) => (
        <PostCard key={p.id} post={p} showSection={showSection} />
      ))}
    </ul>
  );
}

/** 加载中占位 */
export function LoadingList({ rows = 3 }: { rows?: number }) {
  return (
    <ul className="grid gap-3" aria-busy="true" aria-label="加载中">
      {Array.from({ length: rows }).map((_, i) => (
        <li key={i} className="animate-pulse rounded-2xl border border-border-subtle bg-surface-card p-4 sm:p-5">
          <div className="h-3 w-16 rounded-full bg-black/[0.06]" />
          <div className="mt-3 h-4 w-3/4 rounded bg-black/[0.07]" />
          <div className="mt-2 h-3 w-full rounded bg-black/[0.05]" />
          <div className="mt-4 h-3 w-1/3 rounded bg-black/[0.05]" />
        </li>
      ))}
    </ul>
  );
}

/** 错误提示（带重试） */
export function ErrorBox({ message, onRetry, className = "" }: { message: string; onRetry?: () => void; className?: string }) {
  return (
    <div role="alert" className={`rounded-2xl border border-status-danger/30 bg-status-danger/5 px-4 py-6 text-center ${className}`}>
      <p className="text-[14px] font-medium text-text-primary">加载失败</p>
      <p className="mt-1 text-[13px] text-text-secondary">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 cursor-pointer rounded-full bg-purple-primary px-5 py-2 text-[13px] font-semibold text-on-primary hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
        >
          重试
        </button>
      )}
    </div>
  );
}

export const COMMUNITY_RULES = [
  "禁止带单、喊单，禁止任何形式的收费荐股",
  "禁止拉群、导流，禁止留下微信 / QQ / 电话等联系方式及外部链接",
  "禁止承诺收益、保证盈利，禁止传播内幕消息",
  "请理性讨论、友善发言，不进行人身攻击",
] as const;

export function RulesBox({ className = "" }: { className?: string }) {
  return (
    <aside aria-labelledby="forum-rules-title" className={`rounded-2xl border border-border-subtle bg-surface-card p-4 shadow-sm sm:p-5 ${className}`}>
      <h2 id="forum-rules-title" className="flex items-center gap-2 text-[15px] font-semibold text-text-primary">
        <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4 text-purple-primary" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        社区规则
      </h2>
      <ul className="mt-3 space-y-2 text-[13px] leading-relaxed text-text-secondary">
        {COMMUNITY_RULES.map((r) => (
          <li key={r} className="flex gap-2">
            <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-purple-primary" />
            <span>{r}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 rounded-lg bg-purple-light/50 px-3 py-2 text-[12px] leading-relaxed text-text-secondary">
        违规内容将被折叠或删除，情节严重者将限制发言。
      </p>
    </aside>
  );
}
