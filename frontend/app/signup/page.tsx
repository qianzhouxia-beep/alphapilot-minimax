"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";

function SignupRedirect() {
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
    openAuth("signup", next);
    router.replace(next.startsWith("/") ? next : "/cn");
  }, [ready, session, next, openAuth, router]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg-primary">
      <p className="text-[13px] text-text-secondary">正在打开注册…</p>
    </main>
  );
}

export default function SignupPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen flex items-center justify-center bg-bg-primary">
          <p className="text-[13px] text-text-secondary">加载中…</p>
        </main>
      }
    >
      <SignupRedirect />
    </Suspense>
  );
}
