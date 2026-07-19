import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="zh-CN" className="dark">
      <Head>
        <link rel="icon" href="/brand-favicon.png" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <meta charSet="utf-8" />
      </Head>
      <body className="min-h-screen bg-[#0a1422] text-[#EAF2FF] antialiased">
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
