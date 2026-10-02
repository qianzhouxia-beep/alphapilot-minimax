import type { Metadata, Viewport } from "next";
import { AuthShell } from "@/components/AuthShell";
import { SITE_URL } from "@/lib/landing-content";
import { OG_BASE, SEO_DESC as DESC, SEO_TITLE as TITLE } from "@/lib/seo";
import "./globals.css";


export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: TITLE, template: "%s｜AlphaPilot" },
  description: DESC,
  applicationName: "AlphaPilot",
  keywords: ["A股", "量化选股", "股票筛选", "资金流向", "回测", "AlphaPilot"],
  robots: { index: true, follow: true },
  openGraph: OG_BASE,
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESC,
    images: ["/og.png"],
  },
  icons: {
    icon: [
      { url: "/favicon.png?v=284abfe", type: "image/png" },
      { url: "/icon-192.png?v=284abfe", type: "image/png", sizes: "192x192" },
    ],
    apple: [{ url: "/apple-touch-icon.png?v=284abfe", sizes: "180x180" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#F5F5F7",
};

const siteJsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      name: "AlphaPilot",
      url: SITE_URL,
      inLanguage: "zh-CN",
      description: DESC,
    },
    {
      "@type": "Organization",
      name: "AlphaPilot",
      url: SITE_URL,
      logo: `${SITE_URL}/icon-192.png`,
    },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(siteJsonLd) }} />
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
