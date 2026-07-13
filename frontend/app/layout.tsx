import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { LocaleProvider } from "@/lib/i18n";
import { GA_TRACKING_ID } from "@/lib/gtag";

// Use system font stack instead of Google Fonts (avoids GFW blocking fonts.gstatic.com)
// Falls back to: SF Pro / Segoe UI / system-ui for optimal native feel

export const metadata: Metadata = {
  metadataBase: new URL("https://alphapilot.api-tokenmaster.com"),
  title: "AlphaPilot — AI 股票智能决策平台",
  description:
    "AI 智能选股平台，A 股全市场扫描，V12 多模型集成 + 8 Agent 辩论系统。",
  keywords: ["股票分析", "A股", "AI 选股", "短线交易", "量化投资"],
  authors: [{ name: "AlphaPilot" }],
  icons: { icon: "/favicon.png" },
  openGraph: {
    type: "website",
    locale: "zh_CN",
    siteName: "AlphaPilot",
    title: "AlphaPilot — AI 股票智能决策平台",
    description: "AI 智能选股，A 股全市场 V12 多模型集成",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "AlphaPilot" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "AlphaPilot — AI 股票智能决策平台",
    description: "AI 智能选股，A 股全市场 V12 多模型集成",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": "AlphaPilot",
    "description": "AI 智能选股平台，A 股全市场 V12 多模型集成",
    "url": "https://alphapilot.api-tokenmaster.com",
    "applicationCategory": "FinanceApplication",
    "operatingSystem": "Web",
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "USD",
      "description": "7-day free trial"
    }
  };

  return (
    <html lang="zh-CN" className="dark" suppressHydrationWarning>
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        {/* Google Analytics */}
        {GA_TRACKING_ID && (
          <>
            <Script
              strategy="afterInteractive"
              src={`https://www.googletagmanager.com/gtag/js?id=${GA_TRACKING_ID}`}
            />
            <Script
              id="gtag-init"
              strategy="afterInteractive"
              dangerouslySetInnerHTML={{
                __html: `
                  window.dataLayer = window.dataLayer || [];
                  function gtag(){dataLayer.push(arguments);}
                  gtag('js', new Date());
                  gtag('config', '${GA_TRACKING_ID}', {
                    page_path: window.location.pathname,
                  });
                `,
              }}
            />
          </>
        )}
      </head>
      <body className="min-h-screen bg-[#0a1422] text-[#EAF2FF] antialiased">
        <LocaleProvider>
          <AuthProvider>{children}</AuthProvider>
        </LocaleProvider>
      </body>
    </html>
  );
}
