"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { type Quota, getQuota } from "@/lib/forum-api";

/** 当前登录用户的社区信息（昵称、今日额度、是否管理员）。未登录时为 null。 */
export function useForumViewer() {
  const { session } = useAuth();
  const [quota, setQuota] = useState<Quota | null>(null);
  const seq = useRef(0);
  const token = session?.token ?? null;

  const refresh = useCallback(() => {
    const id = ++seq.current;
    if (!token) {
      setQuota(null);
      return;
    }
    getQuota().then(
      (q) => id === seq.current && setQuota(q),
      () => id === seq.current && setQuota(null)
    );
  }, [token]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { quota, isAdmin: !!quota?.is_admin, refresh };
}

/** 登录已失效（接口返回 401）时：先清掉本地过期会话，再弹出登录框，登录后回到 next */
export function useReloginPrompt() {
  const { session, logout, openAuth } = useAuth();
  return useCallback(
    (next: string) => {
      if (session) logout();
      openAuth("login", next);
    },
    [session, logout, openAuth]
  );
}
