// 个股页「讨论」列表：GET /posts?symbol=xxx&sort=hot（只取前 5 条）
"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { ErrorBox, LoadingList, PostList } from "@/components/forum/ForumBits";
import { type ForumPost, describeError, listPosts } from "@/lib/forum-api";

export function StockDiscussion({ symbol }: { symbol: string }) {
  const { session } = useAuth();
  const token = session?.token ?? null;
  const [posts, setPosts] = useState<ForumPost[]>([]);
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [msg, setMsg] = useState("");
  const [tick, setTick] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    if (!symbol) return;
    const n = ++seq.current;
    setState("loading");
    listPosts({ symbol, sort: "hot", pageSize: 5 }).then(
      (r) => {
        if (n !== seq.current) return;
        setPosts(r.items);
        setState("ok");
      },
      (e) => {
        if (n !== seq.current) return;
        setMsg(describeError(e).message);
        setState("error");
      }
    );
  }, [symbol, token, tick]);

  if (state === "loading") return <LoadingList rows={2} />;
  if (state === "error") return <ErrorBox message={msg} onRetry={() => setTick((k) => k + 1)} />;
  return (
    <PostList
      posts={posts}
      emptyTitle="这只股票还没有相关讨论"
      emptyHint="去社区发第一帖，用 $股票名$ 或 $股票代码$ 引用它即可出现在这里。"
    />
  );
}
