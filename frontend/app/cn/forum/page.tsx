// 社区 — 帖子列表（示例数据版，无后端）
"use client";

import { useMemo, useRef, useState } from "react";
import { HeaderBar } from "@/components/HeaderBar";
import { useAuth } from "@/lib/auth";
import { DISCLAIMER_FULL } from "@/lib/disclaimer";
import { Composer } from "@/components/forum/Composer";
import { PinnedBlock, PostList, RulesBox } from "@/components/forum/ForumBits";
import {
  FORUM_IS_MOCK,
  type ForumPost,
  SECTIONS,
  type SectionKey,
  type SortKey,
  listForum,
  safeNickname,
} from "@/lib/forum-mock";

type TabKey = SectionKey | "all";

/** 标签：「全部」放第一位且为默认；其余为 4 个板块 */
const TABS: ReadonlyArray<{ key: TabKey; label: string; desc: string }> = [
  { key: "all", label: "全部", desc: "所有板块的讨论：全站置顶 → 本版置顶 → 其余帖子" },
  ...SECTIONS,
];

export default function ForumPage() {
  const { session, openAuth } = useAuth();
  const [section, setSection] = useState<TabKey>("all");
  const [sort, setSort] = useState<SortKey>("latest");
  const [composing, setComposing] = useState(false);
  const [localPosts, setLocalPosts] = useState<ForumPost[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  // 置顶区（全站置顶 → 本版置顶）+ 普通列表；用户在本页刚发的示例帖排在普通列表最前，永远不会进入置顶区
  const { pinned, posts } = useMemo(() => {
    const { pinned, items } = listForum({ section: section === "all" ? undefined : section, sort });
    const mine = localPosts.filter((p) => section === "all" || p.section === section);
    return { pinned, posts: [...mine, ...items] };
  }, [section, sort, localPosts]);

  const current = TABS.find((s) => s.key === section)!;

  function onPostClick() {
    if (!session) {
      openAuth("login", "/cn/forum");
      return;
    }
    setComposing(true);
  }

  function onTabKey(e: React.KeyboardEvent, i: number) {
    let n = i;
    if (e.key === "ArrowRight") n = (i + 1) % TABS.length;
    else if (e.key === "ArrowLeft") n = (i - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = TABS.length - 1;
    else return;
    e.preventDefault();
    setSection(TABS[n].key);
    tabRefs.current[n]?.focus();
  }

  return (
    <main className="mx-auto min-h-screen max-w-[1200px] px-4 py-3 sm:px-6 sm:py-5 lg:px-8 lg:py-6">
      <HeaderBar market="cn" />

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[26px] font-semibold tracking-tight text-text-primary sm:text-[30px]">社区</h1>
          <p className="mt-1 text-[13px] leading-relaxed text-text-secondary">
            交流方法、复盘名单、互相答疑。讨论仅供学习研究，不构成投资建议。
          </p>
        </div>
        <button
          type="button"
          onClick={onPostClick}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-full bg-purple-primary px-5 py-2.5 text-[14px] font-semibold text-on-primary shadow-sm transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
        >
          <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          发帖
          {!session && <span className="sr-only">（需要登录）</span>}
        </button>
      </div>

      {FORUM_IS_MOCK && (
        <p role="note" className="mb-4 rounded-xl border border-dashed border-border-medium bg-surface-card px-4 py-2.5 text-[12px] leading-relaxed text-text-secondary">
          <strong className="font-semibold text-text-primary">示例数据：</strong>
          社区正在试运行，下面的帖子、回复与昵称均为演示用的虚构内容，不是真实用户发言；发帖不会真正发布。
        </p>
      )}

      {toast && (
        <p role="status" className="mb-4 rounded-xl bg-purple-light px-4 py-2.5 text-[13px] text-purple-primary">{toast}</p>
      )}

      {composing && session && (
        <div className="mb-4">
          <Composer
            defaultSection={section === "all" ? "list" : section}
            author={safeNickname(session.user.full_name)}
            onClose={() => setComposing(false)}
            onPublish={(p) => {
              setLocalPosts((prev) => [p, ...prev]);
              setToast("已加入本页列表（示例版本，不会真正发布）。正式版将采用先发后审。");
              setTimeout(() => setToast(null), 5000);
            }}
          />
        </div>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          {/* 板块 Tabs：窄屏横向滑动，不撑破页面 */}
          <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
            <div role="tablist" aria-label="社区板块（含「全部」）" className="flex w-max gap-1 rounded-full bg-black/[0.045] p-1 sm:w-auto">
              {TABS.map((s, i) => {
                const active = s.key === section;
                return (
                  <button
                    key={s.key}
                    ref={(el) => {
                      tabRefs.current[i] = el;
                    }}
                    role="tab"
                    id={`tab-${s.key}`}
                    aria-selected={active}
                    aria-controls="forum-panel"
                    tabIndex={active ? 0 : -1}
                    onClick={() => setSection(s.key)}
                    onKeyDown={(e) => onTabKey(e, i)}
                    className={`cursor-pointer whitespace-nowrap rounded-full px-4 py-2 text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 ${
                      active ? "bg-white font-semibold text-purple-primary shadow-sm" : "text-text-secondary hover:text-text-primary"
                    }`}
                  >
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <p className="min-w-0 text-[12px] text-text-tertiary">{current.desc}</p>
            <div role="group" aria-label="排序" className="inline-flex shrink-0 gap-0.5 rounded-full bg-black/[0.045] p-0.5">
              {([["latest", "最新"], ["hot", "热门"]] as const).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  aria-pressed={sort === k}
                  onClick={() => setSort(k)}
                  className={`cursor-pointer rounded-full px-3.5 py-1 text-[12px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 ${
                    sort === k ? "bg-white font-medium text-purple-primary shadow-sm" : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div id="forum-panel" role="tabpanel" aria-labelledby={`tab-${section}`} className="mt-4">
            {pinned.length > 0 && (
              <div className="mb-3">
                <PinnedBlock posts={pinned} showSection={section === "all"} />
              </div>
            )}
            <PostList posts={posts} showSection={section === "all"} />
          </div>
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
