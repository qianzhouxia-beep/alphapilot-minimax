"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export function AuthModal() {
  const { authModal, closeAuth, setAuthMode, login, signup, session } = useAuth();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const isSignup = authModal.mode === "signup";

  useEffect(() => {
    if (!authModal.open) return;
    setError(null);
    setLoading(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeAuth();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [authModal.open, closeAuth]);

  useEffect(() => {
    if (authModal.open && session) {
      const next = authModal.next || "/cn";
      closeAuth();
      router.replace(next);
    }
  }, [session, authModal.open, authModal.next, closeAuth, router]);

  if (!authModal.open) return null;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const r = isSignup
      ? await signup(email.trim(), password, fullName.trim())
      : await login(email.trim(), password);
    setLoading(false);
    if (!r.ok) {
      setError(r.error || (isSignup ? "注册失败" : "登录失败"));
      return;
    }
    const next = authModal.next || "/cn";
    closeAuth();
    router.replace(next);
  }

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/30 backdrop-blur-[2px] px-4"
      onClick={closeAuth}
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
    >
      <div
        className="w-full max-w-[400px] rounded-2xl border border-border-subtle bg-surface-card p-6 sm:p-7 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h2 id="auth-modal-title" className="text-[20px] font-semibold text-text-primary">
              {isSignup ? "创建账号" : "登录"}
            </h2>
            <p className="mt-1 text-[12px] text-text-secondary">
              收藏夹与模拟盘仅本人可见
            </p>
          </div>
          <button
            type="button"
            onClick={closeAuth}
            className="rounded-lg px-2 py-1 text-[18px] leading-none text-text-tertiary hover:bg-purple-light/60 hover:text-text-primary transition-colors"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        <div className="mb-5 grid grid-cols-2 gap-1 rounded-xl border border-border-subtle bg-bg-primary p-1">
          <button
            type="button"
            onClick={() => {
              setAuthMode("login");
              setError(null);
            }}
            className={`rounded-lg py-2 text-[13px] font-medium transition-colors ${
              !isSignup
                ? "bg-surface-card text-purple-primary shadow-sm"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            登录
          </button>
          <button
            type="button"
            onClick={() => {
              setAuthMode("signup");
              setError(null);
            }}
            className={`rounded-lg py-2 text-[13px] font-medium transition-colors ${
              isSignup
                ? "bg-surface-card text-purple-primary shadow-sm"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            注册
          </button>
        </div>

        <form onSubmit={onSubmit} className="space-y-3.5">
          {isSignup && (
            <label className="block text-[12px] text-text-secondary">
              昵称
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-border-subtle bg-bg-primary px-3.5 py-2.5 text-[14px] text-text-primary outline-none focus:border-purple-primary/50 focus:ring-2 focus:ring-purple-primary/20"
                placeholder="怎么称呼你"
                autoComplete="name"
              />
            </label>
          )}
          <label className="block text-[12px] text-text-secondary">
            邮箱
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-border-subtle bg-bg-primary px-3.5 py-2.5 text-[14px] text-text-primary outline-none focus:border-purple-primary/50 focus:ring-2 focus:ring-purple-primary/20"
              placeholder="you@example.com"
              autoComplete="email"
              autoFocus
            />
          </label>
          <label className="block text-[12px] text-text-secondary">
            密码{isSignup ? "（至少 8 位）" : ""}
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-border-subtle bg-bg-primary px-3.5 py-2.5 text-[14px] text-text-primary outline-none focus:border-purple-primary/50 focus:ring-2 focus:ring-purple-primary/20"
              placeholder="••••••••"
              autoComplete={isSignup ? "new-password" : "current-password"}
            />
          </label>

          {error && (
            <p className="rounded-lg bg-status-danger/10 px-3 py-2 text-[12px] text-status-danger">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-purple-primary px-4 py-2.5 text-[14px] font-semibold text-on-primary hover:opacity-90 disabled:opacity-60 transition-opacity"
          >
            {loading ? (isSignup ? "注册中…" : "登录中…") : isSignup ? "创建账号" : "登录"}
          </button>
        </form>
      </div>
    </div>
  );
}
