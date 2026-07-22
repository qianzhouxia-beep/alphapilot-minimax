import type { Metadata } from "next";
import { AuthShell } from "@/components/AuthShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "AlphaPilot — 把建仓信号收成可执行清单",
  description:
    "AlphaPilot 综合量化筛选，从全 A 收窄到当日可关注标的。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
