"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** 投资资讯已替换为板块研报 */
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
