import type { Metadata } from "next";
import { OG_BASE } from "@/lib/seo";
import LandingPage from "@/components/landing/LandingPage";

// canonical / og:url 只在首页声明，避免被 /cn/* 等子页继承
export const metadata: Metadata = {
  alternates: { canonical: "/" },
  openGraph: { ...OG_BASE, url: "/" },
};

export default function Page() {
  return <LandingPage />;
}
