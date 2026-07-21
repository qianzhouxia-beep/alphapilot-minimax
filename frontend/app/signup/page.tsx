"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";

function SignupForm() {
  const { signup, session, ready } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/cn";
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (ready && session) {
    router.replace(next);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const r = await signup(email.trim(), password, fullName.trim());
    setLoading(false);
    if (!r.ok) {
      setError(r.error || "注册失败");
      return;
    }
    router.replace(next);
  }

  return (
    <form
      onSubmit={onSubmit}
      className="w-full max-w-md rounded-2xl border border-white/10 bg-white/5 backdrop-blur p-6 sm:p-8 space-y-4"
    >
      <div>
        <h1 className="text-2xl font-semibold text-white">注册 AlphaPilot</h1>
        <p className="mt-1 text-sm text-white/60">注册后仅能查看自己的收藏与模拟盘</p>
      </div>
      <label className="block text-sm text-white/80">
        昵称
        <input
          type="text"
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="mt-1 w-full rounded-lg border border-white/15 bg-black/40 px-3 py-2 text-white outline-none focus:border-sky-400"
        />
      </label>
      <label className="block text-sm text-white/80">
        邮箱
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 w-full rounded-lg border border-white/15 bg-black/40 px-3 py-2 text-white outline-none focus:border-sky-400"
        />
      </label>
      <label className="block text-sm text-white/80">
        密码（至少 8 位）
        <input
          type="password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-lg border border-white/15 bg-black/40 px-3 py-2 text-white outline-none focus:border-sky-400"
        />
      </label>
      {error && <p className="text-sm text-rose-400">{error}</p>}
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-sky-500 hover:bg-sky-400 disabled:opacity-60 px-4 py-2.5 text-sm font-semibold text-white"
      >
        {loading ? "注册中…" : "创建账号"}
      </button>
      <p className="text-center text-sm text-white/55">
        已有账号？{" "}
        <Link href={`/login?next=${encodeURIComponent(next)}`} className="text-sky-400 hover:underline">
          登录
        </Link>
      </p>
    </form>
  );
}

export default function SignupPage() {
  return (
    <main className="min-h-screen flex items-center justify-center px-4 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-950 to-black">
      <Suspense fallback={<div className="text-white/60 text-sm">加载中…</div>}>
        <SignupForm />
      </Suspense>
    </main>
  );
}
