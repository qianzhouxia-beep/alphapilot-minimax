// AlphaPilot Signup — M2 mock auth (Boss pick A, 2026-06-06)

"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function SignupPage() {
  const router = useRouter();
  const { signup } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    const r = await signup(email, password, fullName);
    setSubmitting(false);
    if (!r.ok) {
      setError(r.error ?? "Signup failed");
      return;
    }
    router.push("/");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-6 py-12">
      <div className="glass-strong w-full rounded-2xl p-8">
        <div className="mb-6 text-center">
          <Image src="/brand-logo.png" alt="AlphaPilot" className="mx-auto h-10 w-auto" width={120} height={40} />
          <h1 className="mt-3 text-[24px] font-semibold">创建账户</h1>
          <p className="mt-1 text-[12px] text-[#9FB0C7]">7 天免费试用</p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <Field
            label="姓名"
            type="text"
            value={fullName}
            onChange={setFullName}
            placeholder="请输入姓名"
            autoComplete="name"
          />
          <Field
            label="邮箱"
            type="email"
            value={email}
            onChange={setEmail}
            placeholder="you@example.com"
            autoComplete="email"
          />
          <Field
            label="密码"
            type="password"
            value={password}
            onChange={setPassword}
            placeholder="至少 8 位字符"
            autoComplete="new-password"
          />

          {error && (
            <div className="rounded-lg border border-[#FF5D5D] bg-[rgba(255,93,93,0.08)] p-3 text-[12px] text-[#FF5D5D]">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-[#4DA3FF] py-2.5 text-[14px] font-semibold text-[#00315b] transition-colors hover:bg-[#7ddeff] disabled:opacity-50"
          >
            {submitting ? "创建中..." : "创建账户"}
          </button>
        </form>

        <div className="mt-6 text-center text-[12px] text-[#9FB0C7]">
          已有账户？{" "}
          <Link href="/login" className="text-[#4DA3FF] hover:underline">
            去登录
          </Link>
        </div>

        <p className="mt-6 text-center text-[10px] text-[#6E7C93]">
          模拟登录 (localStorage) · 后续接入真后端
        </p>
      </div>

      <Link href="/" className="mt-6 text-[12px] text-[#9FB0C7] hover:text-[#4DA3FF]">
        ← 返回首页
      </Link>
    </main>
  );
}

function Field({
  label,
  type,
  value,
  onChange,
  placeholder,
  autoComplete,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoComplete?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[11px] uppercase tracking-wider text-[#6E7C93]">
        {label}
      </span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className="w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2 text-[13px] text-[#EAF2FF] placeholder:text-[#6E7C93] focus:border-[#4DA3FF] focus:outline-none"
        required
      />
    </label>
  );
}
