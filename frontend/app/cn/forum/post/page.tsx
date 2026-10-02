// 社区：帖子详情。静态导出下不能用动态路由，所以用查询参数 /cn/forum/post/?id=xxx
"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { HeaderBar } from "@/components/HeaderBar";
import { useAuth } from "@/lib/auth";
import { DISCLAIMER_FULL } from "@/lib/disclaimer";
import { AdminPostBar } from "@/components/forum/AdminBits";
import { AuthorAvatar, AuthorName, ErrorBox, LoadingList, PinTag, RichText, RulesBox, StockChip } from "@/components/forum/ForumBits";
import {
  ForumApiError,
  FORUM_LIMITS,
  type ForumPost,
  type ForumReply,
  REPORT_REASONS,
  SECTION_LABEL,
  adminOfficialReply,
  contentHint,
  createReply,
  deletePost,
  deleteReply,
  describeError,
  favoritePost,
  formatTime,
  getPost,
  likePost,
  likeReply,
  listReplies,
  reportContent,
  stripMarks,
} from "@/lib/forum-api";
import { useForumViewer, useReloginPrompt } from "@/lib/forum-hooks";

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

const Shell = ({ children }: { children: React.ReactNode }) => (
  <main className="mx-auto min-h-screen max-w-[1200px] px-4 py-3 sm:px-6 sm:py-5 lg:px-8 lg:py-6">
    <HeaderBar market="cn" />
    {children}
  </main>
);

function PostDetail() {
  const sp = useSearchParams();
  const id = sp.get("id") || "";
  const router = useRouter();
  const { session, openAuth } = useAuth();
  const { quota, isAdmin } = useForumViewer();
  const relogin = useReloginPrompt();
  const token = session?.token ?? null;
  const here = `/cn/forum/post/?id=${encodeURIComponent(id)}`;

  const [post, setPost] = useState<ForumPost | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "error" | "missing">("loading");
  const [errMsg, setErrMsg] = useState("");
  const [expand, setExpand] = useState(false);
  const [reload, setReload] = useState(0);

  const [replies, setReplies] = useState<ForumReply[]>([]);
  const [rTotal, setRTotal] = useState(0);
  const [rPage, setRPage] = useState(1);
  const [rState, setRState] = useState<"loading" | "ok" | "error">("loading");
  const [rErr, setRErr] = useState("");
  const [rMore, setRMore] = useState<"idle" | "loading" | "error">("idle");

  const [notice, setNotice] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [reason, setReason] = useState<string>(REPORT_REASONS[0].code);
  const [reportMsg, setReportMsg] = useState<string | null>(null);
  const [replyText, setReplyText] = useState("");
  const [replyErr, setReplyErr] = useState<string | null>(null);
  const [replyBusy, setReplyBusy] = useState(false);
  const [asOfficial, setAsOfficial] = useState(false);
  const seq = useRef(0);

  // 帖子详情（带 token 才有 viewer 标志；登录状态变化时重新拉取）
  useEffect(() => {
    if (!id) {
      setState("missing");
      return;
    }
    const n = ++seq.current;
    setState("loading");
    setRState("loading");
    getPost(id, expand).then(
      (p) => {
        if (n !== seq.current) return;
        setPost(p);
        setState("ok");
      },
      (e) => {
        if (n !== seq.current) return;
        if (e instanceof ForumApiError && (e.code === "POST_NOT_FOUND" || e.code === "NOT_FOUND")) setState("missing");
        else {
          setErrMsg(describeError(e).message);
          setState("error");
        }
      }
    );
    listReplies(id, { page: 1, expand }).then(
      (r) => {
        if (n !== seq.current) return;
        setReplies(r.items);
        setRTotal(r.total);
        setRPage(1);
        setRMore("idle");
        setRState("ok");
      },
      (e) => {
        if (n !== seq.current) return;
        setRErr(describeError(e).message);
        setRState("error");
      }
    );
  }, [id, token, expand, reload]);

  const loadMoreReplies = useCallback(async () => {
    setRMore("loading");
    try {
      const r = await listReplies(id, { page: rPage + 1, expand });
      setReplies((prev) => [...prev, ...r.items.filter((x) => !prev.some((y) => y.id === x.id))]);
      setRTotal(r.total);
      setRPage(rPage + 1);
      setRMore("idle");
    } catch {
      setRMore("error");
    }
  }, [id, rPage, expand]);

  /** 统一处理操作失败：未登录弹登录框，其余显示中文提示 */
  function fail(e: unknown) {
    const d = describeError(e);
    if (d.action === "login") relogin(here);
    setActionErr(d.message);
  }
  const need = (fn: () => void | Promise<void>) => () => {
    setActionErr(null);
    setNotice(null);
    if (!session) return openAuth("login", here);
    void Promise.resolve(fn()).catch(fail);
  };

  const patchViewer = (p: ForumPost, v: Partial<NonNullable<ForumPost["viewer"]>>): ForumPost => ({
    ...p,
    viewer: { liked: false, reported: false, ...(p.viewer ?? {}), ...v },
  });

  const toggleLike = need(async () => {
    if (!post) return;
    const r = await likePost(post.id, !post.viewer?.liked);
    setPost((p) => (p ? { ...patchViewer(p, { liked: r.liked }), like_count: r.like_count } : p));
  });
  const toggleFav = need(async () => {
    if (!post) return;
    const r = await favoritePost(post.id, !post.viewer?.favorited);
    setPost((p) => (p ? patchViewer(p, { favorited: r.favorited }) : p));
  });
  const toggleReplyLike = (r: ForumReply) =>
    need(async () => {
      const x = await likeReply(r.id, !r.viewer?.liked);
      setReplies((list) =>
        list.map((y) => (y.id === r.id ? { ...y, like_count: x.like_count, viewer: { reported: false, ...(y.viewer ?? {}), liked: x.liked } } : y))
      );
    });

  const submitReport = need(async () => {
    if (!post) return;
    try {
      const r = await reportContent({ target_type: "post", target_id: post.id, reason });
      setPost((p) => (p ? patchViewer(p, { reported: true }) : p));
      setReportMsg(r.folded ? "已收到你的举报，该内容因举报较多已被折叠，等待人工复核。" : "已收到你的举报，我们会尽快处理。");
    } catch (e) {
      if (e instanceof ForumApiError && e.code === "ALREADY_REPORTED") {
        setPost((p) => (p ? patchViewer(p, { reported: true }) : p));
        setReportMsg(describeError(e).message);
      } else throw e;
    }
  });

  const removePost = need(async () => {
    if (!post || !window.confirm("确定删除这条帖子吗？删除后无法恢复。")) return;
    await deletePost(post.id);
    router.push("/cn/forum/");
  });
  const removeReply = (r: ForumReply) =>
    need(async () => {
      if (!window.confirm("确定删除这条回复吗？")) return;
      await deleteReply(r.id);
      setReplies((list) => list.filter((y) => y.id !== r.id));
      setRTotal((n) => Math.max(0, n - 1));
      setPost((p) => (p ? { ...p, reply_count: Math.max(0, p.reply_count - 1) } : p));
    });

  async function submitReply(e: React.FormEvent) {
    e.preventDefault();
    if (replyBusy || !post) return;
    const text = replyText.trim();
    if (!text) return setReplyErr("回复内容不能为空。");
    if (text.length > FORUM_LIMITS.replyMax) return setReplyErr(`回复最多 ${FORUM_LIMITS.replyMax} 字。`);
    setReplyErr(null);
    setReplyBusy(true);
    try {
      const r = asOfficial && isAdmin ? await adminOfficialReply(post.id, text) : await createReply(post.id, text);
      const reply = r.reply;
      setReplies((list) => [...list, reply]);
      setRTotal((n) => n + 1);
      setPost((p) => (p ? { ...p, reply_count: p.reply_count + 1 } : p));
      setReplyText("");
      if ("needs_review" in r && r.needs_review) setNotice("回复已发布，内容会进入人工复核。");
    } catch (ex) {
      const d = describeError(ex);
      if (d.action === "login") relogin(here);
      setReplyErr(d.message);
    } finally {
      setReplyBusy(false);
    }
  }

  if (state === "loading") {
    return (
      <Shell>
        <LoadingList rows={2} />
      </Shell>
    );
  }
  if (state === "error") {
    return (
      <Shell>
        <ErrorBox message={errMsg} onRetry={() => setReload((k) => k + 1)} />
        <p className="mt-4 text-center"><Link href="/cn/forum/" className="text-[13px] text-purple-primary">返回社区</Link></p>
      </Shell>
    );
  }
  if (state === "missing" || !post) {
    return (
      <Shell>
        <div className="rounded-2xl border border-dashed border-border-medium px-4 py-14 text-center">
          <p className="text-[16px] font-semibold text-text-primary">没有找到这篇帖子</p>
          <p className="mt-1 text-[13px] text-text-secondary">它可能已被删除，或链接有误。</p>
          <Link href="/cn/forum/" className="mt-4 inline-block rounded-full bg-purple-primary px-5 py-2 text-[13px] font-semibold text-on-primary">
            返回社区
          </Link>
        </div>
      </Shell>
    );
  }

  const folded = post.status === "folded";
  const hiddenBody = folded && !post.body;
  const mine = !!post.viewer?.is_mine;
  const liked = !!post.viewer?.liked;
  const faved = !!post.viewer?.favorited;
  const hint = replyText ? contentHint(replyText) : null;

  return (
    <Shell>
      <nav aria-label="面包屑" className="mb-3 text-[13px] text-text-secondary">
        <Link href="/cn/forum/" className="hover:text-purple-primary">← 社区</Link>
        <span aria-hidden className="mx-2 text-text-disabled">/</span>
        <span>{post.section_label || SECTION_LABEL[post.section]}</span>
      </nav>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-4">
          <article className={`rounded-2xl border p-4 shadow-sm sm:p-6 ${post.is_official ? "border-purple-primary/20 bg-purple-light/30" : "border-border-subtle bg-surface-card"}`}>
            <div className="flex flex-wrap items-center gap-2 text-[12px]">
              <PinTag scope={post.pin_scope} />
              <span className="rounded-full bg-black/[0.05] px-2 py-0.5 text-text-secondary">{post.section_label || SECTION_LABEL[post.section]}</span>
              {folded && <span className="rounded-full bg-black/[0.05] px-2 py-0.5 text-text-tertiary">已折叠</span>}
            </div>
            <h1 className="mt-2 break-words text-[22px] font-semibold leading-snug tracking-tight text-text-primary sm:text-[26px]">
              {stripMarks(post.title)}
            </h1>
            <div className="mt-3 flex items-center gap-3 text-[13px] text-text-tertiary">
              <AuthorAvatar author={post.author} size={36} />
              <div className="min-w-0">
                <div className="flex min-w-0 flex-wrap items-center gap-2 font-medium text-text-primary">
                  {post.author.is_official ? <AuthorName author={post.author} /> : <span className="truncate">{post.author.nickname}</span>}
                </div>
                <time dateTime={post.created_at}>{formatTime(post.created_at)}</time>
              </div>
            </div>

            {hiddenBody ? (
              <div className="mt-4 rounded-xl border border-dashed border-border-medium bg-black/[0.03] px-4 py-5 text-center">
                <p className="text-[13px] text-text-secondary">{post.fold_reason_label || "该帖已被折叠。"}</p>
                <button
                  type="button"
                  onClick={() => setExpand(true)}
                  className="mt-2 cursor-pointer rounded-full border border-border-medium bg-white px-4 py-1.5 text-[12px] text-text-primary hover:border-purple-primary/40 hover:text-purple-primary"
                >
                  仍要查看原文
                </button>
              </div>
            ) : (
              <RichText text={post.body ?? ""} stocks={post.stocks} className="mt-4 text-[15px] leading-[1.8] text-text-primary" />
            )}

            {post.stocks.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border-subtle pt-3">
                <span className="text-[12px] text-text-tertiary">相关股票</span>
                {post.stocks.map((s) => (
                  <StockChip key={s.code} name={s.name} code={s.code} />
                ))}
              </div>
            )}

            <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border-subtle pt-4">
              <ActionButton pressed={liked} label={liked ? "取消点赞" : "点赞"} onClick={toggleLike} count={post.like_count}>
                <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M7 11v9H4v-9h3zm0 0 4-7a2 2 0 0 1 2 2v3h5.4a2 2 0 0 1 2 2.3l-1 6A2 2 0 0 1 17.4 19H7" />
                </svg>
                赞
              </ActionButton>
              <ActionButton pressed={faved} label={faved ? "取消收藏" : "收藏"} onClick={toggleFav}>
                <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill={faved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 3h12v18l-6-4-6 4V3z" />
                </svg>
                {faved ? "已收藏" : "收藏"}
              </ActionButton>
              <span className="ml-auto inline-flex items-center gap-1">
                {mine && (
                  <button type="button" onClick={removePost} className="cursor-pointer rounded-full px-3 py-1.5 text-[13px] text-text-tertiary hover:text-status-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50">
                    删除
                  </button>
                )}
                {!mine && (
                  <button
                    type="button"
                    aria-expanded={reportOpen}
                    aria-controls="report-panel"
                    onClick={need(() => setReportOpen((v) => !v))}
                    className="inline-flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] text-text-tertiary transition-colors hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
                  >
                    <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M5 21V4m0 0h11l-2 4 2 4H5" />
                    </svg>
                    {post.viewer?.reported ? "已举报" : "举报"}
                  </button>
                )}
              </span>
            </div>

            {actionErr && <p role="alert" className="mt-3 rounded-xl border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-[13px] text-status-danger">{actionErr}</p>}
            {notice && <p role="status" className="mt-3 rounded-xl bg-purple-light px-3 py-2 text-[13px] text-purple-primary">{notice}</p>}

            {reportOpen && (
              <div id="report-panel" className="mt-3 rounded-xl border border-border-subtle bg-bg-primary/60 p-4">
                {reportMsg || post.viewer?.reported ? (
                  <p role="status" className="text-[13px] text-text-secondary">
                    {reportMsg ?? "你已经举报过这条内容了。"} 累计 {FORUM_LIMITS.reportFoldThreshold} 次举报会自动折叠并进入人工审核。
                  </p>
                ) : (
                  <fieldset>
                    <legend className="text-[13px] font-medium text-text-primary">举报原因</legend>
                    <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                      {REPORT_REASONS.map((r) => (
                        <label key={r.code} className="flex cursor-pointer items-center gap-2 text-[13px] text-text-secondary">
                          <input type="radio" name="report-reason" checked={reason === r.code} onChange={() => setReason(r.code)} className="accent-[#7C5CFC]" />
                          {r.label}
                        </label>
                      ))}
                    </div>
                    <div className="mt-3 flex gap-2">
                      <button type="button" onClick={submitReport} className="cursor-pointer rounded-full bg-purple-primary px-4 py-1.5 text-[13px] font-semibold text-on-primary hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50">
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

            {isAdmin && (
              <div className="mt-4">
                <AdminPostBar post={post} onChanged={() => setReload((k) => k + 1)} onDeleted={() => router.push("/cn/forum/")} />
              </div>
            )}
          </article>

          <section aria-labelledby="replies-title" className="rounded-2xl border border-border-subtle bg-surface-card p-4 shadow-sm sm:p-6">
            <h2 id="replies-title" className="text-[16px] font-semibold text-text-primary">
              回复 <span className="text-text-tertiary">{rState === "ok" ? rTotal : post.reply_count}</span>
            </h2>

            {rState === "loading" && <div className="mt-3"><LoadingList rows={2} /></div>}
            {rState === "error" && <ErrorBox className="mt-3" message={rErr} onRetry={() => setReload((k) => k + 1)} />}
            {rState === "ok" && replies.length === 0 && (
              <p className="mt-3 rounded-xl border border-dashed border-border-medium px-4 py-6 text-center text-[13px] text-text-secondary">还没有回复，来说两句吧。</p>
            )}
            {rState === "ok" && replies.length > 0 && (
              <ol className="mt-3 divide-y divide-border-subtle">
                {replies.map((r, i) => (
                  <li key={r.id} className="flex gap-3 py-4 first:pt-1">
                    <AuthorAvatar author={r.author} size={32} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-2 text-[13px]">
                        {r.author.is_official ? <AuthorName author={r.author} /> : <span className="font-medium text-text-primary">{r.author.nickname}</span>}
                        <time dateTime={r.created_at} className="text-[12px] text-text-tertiary">{formatTime(r.created_at)}</time>
                        <span className="ml-auto text-[12px] text-text-disabled">#{i + 1}</span>
                      </div>
                      {r.status === "folded" && !r.body ? (
                        <p className="mt-1 text-[13px] text-text-tertiary">{r.fold_reason_label || "该回复已被折叠。"}</p>
                      ) : (
                        <RichText text={r.body} stocks={post.stocks} className="mt-1 text-[14px] leading-relaxed text-text-primary" />
                      )}
                      <div className="mt-1.5 flex items-center gap-3">
                        <button
                          type="button"
                          aria-pressed={!!r.viewer?.liked}
                          onClick={toggleReplyLike(r)}
                          className={`inline-flex cursor-pointer items-center gap-1 rounded-full px-2 py-0.5 text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 ${
                            r.viewer?.liked ? "text-purple-primary" : "text-text-tertiary hover:text-purple-primary"
                          }`}
                        >
                          赞 <span className="tabular-nums">{r.like_count}</span>
                        </button>
                        {r.viewer?.is_mine && (
                          <button type="button" onClick={removeReply(r)} className="cursor-pointer text-[12px] text-text-tertiary hover:text-status-danger focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50">
                            删除
                          </button>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {rState === "ok" && replies.length < rTotal && (
              <div className="mt-2 text-center">
                {rMore === "error" && <p role="alert" className="mb-2 text-[12px] text-status-danger">加载更多回复失败，请重试。</p>}
                <button type="button" onClick={loadMoreReplies} disabled={rMore === "loading"} className="cursor-pointer rounded-full border border-border-medium bg-white px-5 py-1.5 text-[12px] text-text-primary hover:border-purple-primary/40 disabled:opacity-50">
                  {rMore === "loading" ? "加载中" : `加载更多回复（${replies.length} / ${rTotal}）`}
                </button>
              </div>
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
                  {hint && !replyErr && <p className="mt-2 text-[12px] text-text-secondary">{hint}</p>}
                  {replyErr && <p role="alert" className="mt-2 text-[13px] text-status-danger">{replyErr}</p>}
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                    {isAdmin ? (
                      <label className="flex cursor-pointer items-center gap-2 text-[12px] text-text-secondary">
                        <input type="checkbox" checked={asOfficial} onChange={(e) => setAsOfficial(e.target.checked)} className="accent-[#7C5CFC]" />
                        以官方身份回复
                      </label>
                    ) : (
                      <p className="text-[11px] text-text-tertiary">{quota ? `回复昵称：${quota.nickname}` : "违规内容会被折叠或删除"}</p>
                    )}
                    <button type="submit" disabled={replyBusy} className="cursor-pointer rounded-full bg-purple-primary px-5 py-2 text-[13px] font-semibold text-on-primary hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 disabled:opacity-40">
                      {replyBusy ? "发送中" : "回复"}
                    </button>
                  </div>
                </form>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-purple-light/40 px-4 py-3">
                  <p className="text-[13px] text-text-secondary">登录后可以回复、点赞和收藏。</p>
                  <button
                    type="button"
                    onClick={() => openAuth("login", here)}
                    className="cursor-pointer rounded-full bg-purple-primary px-4 py-1.5 text-[13px] font-semibold text-on-primary hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
                  >
                    登录后回复
                  </button>
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
    </Shell>
  );
}

export default function ForumPostPage() {
  return (
    <Suspense
      fallback={
        <Shell>
          <LoadingList rows={2} />
        </Shell>
      }
    >
      <PostDetail />
    </Suspense>
  );
}
