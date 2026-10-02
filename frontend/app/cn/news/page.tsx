"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** “资讯”入口已并入“板块研报”：保留旧路由 /cn/news，统一跳转到 /cn/sectors */
export default function NewsRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/cn/sectors");
  }, [router]);
  return (
    <main className="min-h-screen flex items-center justify-center text-[13px] text-text-tertiary">
      正在跳转到板块研报…
    </main>
  );
}
