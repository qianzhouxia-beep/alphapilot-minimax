import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "AlphaPilot — 把建仓信号收成可执行清单",
  description:
    "AlphaPilot V3.1 硬门控漏斗 + VM2.5 三模型打分，从全 A 收窄到当日可关注标的。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
