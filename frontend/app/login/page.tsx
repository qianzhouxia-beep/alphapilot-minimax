"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";

function LoginRedirect() {
  const { openAuth, session, ready } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/cn";

  useEffect(() => {
    if (!ready) return;
    if (session) {
      router.replace(next);
      return;
    }
    openAuth("login", next);
    router.replace(next.startsWith("/") ? next : "/cn");
  }, [ready, session, next, openAuth, router]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg-primary">
      <p className="text-[13px] text-text-secondary">正在打开登录…</p>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen flex items-center justify-center bg-bg-primary">
          <p className="text-[13px] text-text-secondary">加载中…</p>
        </main>
      }
    >
      <LoginRedirect />
    </Suspense>
  );
}
