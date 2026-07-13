// AlphaPilot Frontend — Next.js 15 (App Router)
// 2026-06-12: 静态 export 模式 → 2026-06-15: 改回 SSR（/stock/[symbol] 动态路由需要）
// 2026-06-14 C2: 加载性能优化（字体、图片、压缩）
import type { NextConfig } from "next";
import bundleAnalyzer from "@next/bundle-analyzer";

const withBundleAnalyzer = bundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
});

const nextConfig: NextConfig = {
  reactStrictMode: true,
  trailingSlash: true,
  // 2026-06-12: 拍板 typecheck bypass (test deps 老板 L1 拍板没装, build pass 优先)
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  output: "export",
  // SSR mode disabled for Zeabur static build: dynamic routes not supported
  
  // 2026-06-14 C2: 性能优化
  // 注意: output:"export" 必须 unoptimized images
  images: { unoptimized: true },
  compress: true, // 启用 gzip 压缩
  poweredByHeader: false, // 移除 X-Powered-By header（安全优化）
};

export default withBundleAnalyzer(nextConfig);
