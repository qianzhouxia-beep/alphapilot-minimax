// Server Component: generateStaticParams for static export (output: export)
// Page is "use client" and cannot export generateStaticParams directly

export function generateStaticParams() {
  // Top 15 A-share stocks by market cap (codes without suffix — client normalizes to SH/SZ)
  return [
    "600519", "601857", "601939", "601988", "601288",
    "600036", "601318", "600900", "601166", "600276",
    "000858", "000333", "002415", "300750", "000001",
  ].map((symbol) => ({ symbol }));
}

export default function CNSymbolLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
