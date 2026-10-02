// 管理员最小控件（仅当 GET /me/quota 返回 is_admin=true 时由页面渲染；后端另有 403 ADMIN_ONLY 兜底）
"use client";

import { useState } from "react";
import {
  type ForumPost,
  SECTIONS,
  type SectionKey,
  adminCreateOfficial,
  adminPin,
  adminSetStatus,
  adminUnpin,
  describeError,
} from "@/lib/forum-api";

const field =
  "w-full rounded-xl border border-border-subtle bg-white px-3 py-2 text-[14px] text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50";

/** 发官方帖（可选置顶范围）。官方身份由服务器按管理员身份确定，不接受前端传入。 */
export function OfficialComposer({
  defaultSection,
  onDone,
  onClose,
}: {
  defaultSection: SectionKey;
  onDone: () => void;
  onClose: () => void;
}) {
  const [section, setSection] = useState<SectionKey>(defaultSection);
  const [pin, setPin] = useState<"none" | "global" | "section">("none");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (!title.trim() || !body.trim()) return setErr("标题和正文都不能为空。");
    setBusy(true);
    setErr(null);
    try {
      await adminCreateOfficial({ section, title: title.trim(), body: body.trim(), pin_scope: pin });
      onDone();
      onClose();
    } catch (ex) {
      setErr(describeError(ex).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="发官方帖" className="rounded-2xl border border-purple-primary/30 bg-purple-light/30 p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[16px] font-semibold text-text-primary">发官方帖（管理员）</h2>
        <button type="button" onClick={onClose} className="cursor-pointer rounded-full px-3 py-1 text-[12px] text-text-secondary hover:bg-black/[0.05]">取消</button>
      </div>
      <form onSubmit={submit} className="mt-3 space-y-3" noValidate>
        <div className="flex flex-wrap gap-3">
          <label className="text-[12px] text-text-secondary">
            板块
            <select value={section} onChange={(e) => setSection(e.target.value as SectionKey)} className={`${field} mt-1`}>
              {SECTIONS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
          <label className="text-[12px] text-text-secondary">
            置顶
            <select value={pin} onChange={(e) => setPin(e.target.value as typeof pin)} className={`${field} mt-1`}>
              <option value="none">不置顶</option>
              <option value="section">本版置顶</option>
              <option value="global">全站置顶</option>
            </select>
          </label>
        </div>
        <input aria-label="标题" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="标题" className={field} />
        <textarea aria-label="正文" value={body} onChange={(e) => setBody(e.target.value)} rows={5} placeholder="正文" className={`${field} resize-y`} />
        {err && <p role="alert" className="rounded-xl border border-status-danger/30 bg-status-danger/5 px-3 py-2 text-[13px] text-status-danger">{err}</p>}
        <div className="text-right">
          <button type="submit" disabled={busy} className="cursor-pointer rounded-full bg-purple-primary px-5 py-2 text-[13px] font-semibold text-on-primary hover:opacity-90 disabled:opacity-40">
            {busy ? "发布中" : "发布官方帖"}
          </button>
        </div>
      </form>
    </section>
  );
}

/** 帖子详情页上的管理员操作条：置顶 / 取消置顶 / 折叠 / 恢复 / 删除 */
export function AdminPostBar({ post, onChanged, onDeleted }: { post: ForumPost; onChanged: () => void; onDeleted: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>, after: () => void = onChanged) {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      await fn();
      after();
    } catch (ex) {
      setErr(describeError(ex).message);
    } finally {
      setBusy(false);
    }
  }

  const btn =
    "cursor-pointer rounded-full border border-border-medium bg-white px-3 py-1 text-[12px] text-text-primary hover:border-purple-primary/40 hover:text-purple-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 disabled:cursor-not-allowed disabled:opacity-40";
  const pinned = post.pin_scope !== "none";
  const folded = post.status === "folded";

  return (
    <div role="group" aria-label="管理员操作" className="rounded-xl border border-dashed border-purple-primary/40 bg-purple-light/30 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12px] font-medium text-purple-primary">管理员</span>
        {pinned ? (
          <button type="button" disabled={busy} className={btn} onClick={() => run(() => adminUnpin(post.id))}>取消置顶</button>
        ) : (
          <>
            <button type="button" disabled={busy} className={btn} onClick={() => run(() => adminPin(post.id, "section"))}>本版置顶</button>
            <button type="button" disabled={busy} className={btn} onClick={() => run(() => adminPin(post.id, "global"))}>全站置顶</button>
          </>
        )}
        <button type="button" disabled={busy} className={btn} onClick={() => run(() => adminSetStatus(post.id, folded ? "unfold" : "fold"))}>
          {folded ? "取消折叠" : "折叠（隐藏）"}
        </button>
        <button
          type="button"
          disabled={busy}
          className={`${btn} !text-status-danger`}
          onClick={() => {
            if (window.confirm("确定删除这条帖子吗？")) run(() => adminSetStatus(post.id, "delete"), onDeleted);
          }}
        >
          删除
        </button>
      </div>
      {post.admin && (
        <p className="mt-1.5 text-[11px] text-text-tertiary">
          举报 {post.admin.report_count} 次{post.admin.needs_review ? "，待人工复核" : ""}
        </p>
      )}
      {err && <p role="alert" className="mt-1.5 text-[12px] text-status-danger">{err}</p>}
    </div>
  );
}
