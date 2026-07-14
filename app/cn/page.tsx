"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

export default function CNDashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/cn/recommend")
      .then(r => r.json())
      .then(d => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <main className="min-h-screen bg-[#0a0f1c] text-white p-4">
      <h1 className="text-2xl font-bold mb-4">AlphaPilot</h1>
      {loading ? (
        <p>Loading...</p>
      ) : (
        <pre className="text-sm">{JSON.stringify(data, null, 2)}</pre>
      )}
    </main>
  );
}
