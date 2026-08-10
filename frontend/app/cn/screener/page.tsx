// AlphaPilot A 股智能选股：已合并进 Dashboard 侧栏，本页重定向
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { HeaderBar } from "@/components/HeaderBar";

export default function CNScreener() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/cn");
  }, [router]);

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />
      <div className="flex flex-col items-center justify-center py-32">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-border-subtle border-t-purple-primary" />
        <p className="mt-5 text-[14px] text-text-secondary">
          智能选股已合并进 A 股首页侧栏，正在跳转…
        </p>
      </div>
    </main>
  );
}
