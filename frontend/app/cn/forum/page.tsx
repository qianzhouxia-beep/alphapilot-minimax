// 社区：帖子列表（真实接口 /api/v1/cn/forum/posts）
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { HeaderBar } from "@/components/HeaderBar";
import { useAuth } from "@/lib/auth";
import { DISCLAIMER_FULL } from "@/lib/disclaimer";
import { Composer } from "@/components/forum/Composer";
import { OfficialComposer } from "@/components/forum/AdminBits";
import { ErrorBox, LoadingList, PinnedBlock, PostList, RulesBox } from "@/components/forum/ForumBits";
import {
  type CreatePostResponse,
  type ForumPost,
  SECTIONS,
  type SortKey,
  type TabKey,
  describeError,
  listPosts,
} from "@/lib/forum-api";
import { useForumViewer } from "@/lib/forum-hooks";

/** 标签：「全部」放第一位且为默认；其余为 4 个板块 */
const TABS: ReadonlyArray<{ key: TabKey; label: string; desc: string }> = [
  { key: "all", label: "全部", desc: "所有板块的讨论：全站置顶、本版置顶，再到其余帖子" },
  ...SECTIONS,
];

const PAGE_SIZE = 20;

export default function ForumPage() {
  const { session, openAuth } = useAuth();
  const { quota, isAdmin, refresh: refreshViewer } = useForumViewer();
  const [section, setSection] = useState<TabKey>("all");
  const [sort, setSort] = useState<SortKey>("latest");
  const [composing, setComposing] = useState(false);
  const [officialOpen, setOfficialOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const [pinned, setPinned] = useState<ForumPost[]>([]);
  const [posts, setPosts] = useState<ForumPost[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [more, setMore] = useState<"idle" | "loading" | "error">("idle");
  const [errMsg, setErrMsg] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const seq = useRef(0);
  const token = session?.token ?? null;

  // 切换板块 / 排序 / 登录状态 / 手动刷新时重新拉第 1 页（带 token，viewer 标志才有值）
  useEffect(() => {
    const id = ++seq.current;
    setStatus("loading");
    listPosts({ section, sort, page: 1, pageSize: PAGE_SIZE }).then(
      (r) => {
        if (id !== seq.current) return;
        setPinned(r.pinned ?? []);
        setPosts(r.items);
        setTotal(r.total);
        setPage(1);
        setMore("idle");
        setStatus("ok");
      },
      (e) => {
        if (id !== seq.current) return;
        setErrMsg(describeError(e).message);
        setStatus("error");
      }
    );
  }, [section, sort, token, reloadKey]);

  const loadMore = useCallback(async () => {
    const id = seq.current;
    setMore("loading");
    try {
      const r = await listPosts({ section, sort, page: page + 1, pageSize: PAGE_SIZE });
      if (id !== seq.current) return;
      setPosts((prev) => [...prev, ...r.items.filter((x) => !prev.some((y) => y.id === x.id))]);
      setPage(page + 1);
      setMore("idle");
    } catch {
      if (id === seq.current) setMore("error");
    }
  }, [section, sort, page]);

  const current = TABS.find((s) => s.key === section)!;

  function flash(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  }

  function onPostClick() {
    if (!session) {
      openAuth("login", "/cn/forum/");
      return;
    }
    setComposing(true);
  }

  function onPublished(r: CreatePostResponse) {
    flash(r.needs_review ? "发布成功，内容会进入人工复核。" : "发布成功。");
    refreshViewer();
    setReloadKey((k) => k + 1);
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
        <div className="flex flex-wrap items-center gap-2">
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
          {isAdmin && (
            <button
              type="button"
              onClick={() => setOfficialOpen(true)}
              className="inline-flex cursor-pointer items-center rounded-full border border-purple-primary/40 bg-white px-4 py-2.5 text-[13px] font-medium text-purple-primary hover:bg-purple-light/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
            >
              发官方帖
            </button>
          )}
        </div>
      </div>

      {toast && (
        <p role="status" className="mb-4 rounded-xl bg-purple-light px-4 py-2.5 text-[13px] text-purple-primary">{toast}</p>
      )}

      {composing && session && (
        <div className="mb-4">
          <Composer
            defaultSection={section === "all" ? "list" : section}
            quota={quota}
            onClose={() => setComposing(false)}
            onPublished={onPublished}
          />
        </div>
      )}

      {officialOpen && isAdmin && (
        <div className="mb-4">
          <OfficialComposer
            defaultSection={section === "all" ? "feedback" : section}
            onClose={() => setOfficialOpen(false)}
            onDone={() => {
              flash("官方帖已发布。");
              setReloadKey((k) => k + 1);
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
            {status === "loading" && <LoadingList />}
            {status === "error" && <ErrorBox message={errMsg} onRetry={() => setReloadKey((k) => k + 1)} />}
            {status === "ok" && (
              <>
                {pinned.length > 0 && (
                  <div className="mb-3">
                    <PinnedBlock posts={pinned} showSection={section === "all"} />
                  </div>
                )}
                <PostList posts={posts} showSection={section === "all"} />
                {posts.length < total && (
                  <div className="mt-4 text-center">
                    {more === "error" && <p role="alert" className="mb-2 text-[12px] text-status-danger">加载更多失败，请重试。</p>}
                    <button
                      type="button"
                      onClick={loadMore}
                      disabled={more === "loading"}
                      className="cursor-pointer rounded-full border border-border-medium bg-white px-6 py-2 text-[13px] text-text-primary hover:border-purple-primary/40 hover:text-purple-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 disabled:opacity-50"
                    >
                      {more === "loading" ? "加载中" : `加载更多（已显示 ${posts.length} / ${total}）`}
                    </button>
                  </div>
                )}
              </>
            )}
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
