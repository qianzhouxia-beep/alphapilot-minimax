"use client";

/**
 * 真实后端鉴权：POST /api/v1/auth/login|signup，JWT 存 localStorage
 */

import { createContext, useContext, useEffect, useState } from "react";

export type AuthUser = {
  id: number | string;
  email: string;
  full_name: string;
  plan: "free" | "pro" | "elite" | string;
  credits?: number;
  created_at?: string;
  is_owner?: boolean;
};

type Session = {
  token: string;
  user: AuthUser;
};

type AuthState = {
  session: Session | null;
  ready: boolean;
  signup: (email: string, password: string, full_name: string) => Promise<{ ok: boolean; error?: string }>;
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => void;
};

const STORAGE_KEY = "alphapilot_session";
const AuthContext = createContext<AuthState | null>(null);

function apiBase(): string {
  if (typeof window !== "undefined" && window.location.hostname === "localhost") {
    return "https://alphapilot.api-tokenmaster.com";
  }
  return "";
}

function loadSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Session;
    if (!s?.token || !s?.user?.email) return null;
    // 清掉旧 mock 会话，避免带着假 token 打私有接口刷 401
    if (
      s.token.includes("mock_signature") ||
      String(s.user.id).startsWith("mock_")
    ) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

function saveSession(s: Session | null) {
  if (typeof window === "undefined") return;
  if (s === null) {
    localStorage.removeItem(STORAGE_KEY);
  } else {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  }
}

export function getAuthToken(): string | null {
  return loadSession()?.token ?? null;
}

async function authRequest(
  path: string,
  body: Record<string, string>,
): Promise<{ ok: true; session: Session } | { ok: false; error: string }> {
  try {
    const res = await fetch(`${apiBase()}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data?.detail;
      const msg = typeof detail === "string" ? detail : res.statusText || "请求失败";
      return { ok: false, error: msg };
    }
    if (!data?.token || !data?.user) {
      return { ok: false, error: "登录响应异常" };
    }
    const session: Session = {
      token: data.token,
      user: {
        id: data.user.id,
        email: data.user.email,
        full_name: data.user.full_name || data.user.email?.split("@")[0] || "",
        plan: data.user.plan || "free",
        credits: 0,
        created_at: data.user.created_at,
        is_owner: !!data.user.is_owner,
      },
    };
    return { ok: true, session };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "网络错误" };
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const s = loadSession();
    setSession(s);
    setReady(true);
    if (!s?.token) return;
    // 校验 token，失效则清会话
    fetch(`${apiBase()}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${s.token}` },
      cache: "no-store",
    })
      .then(async (r) => {
        if (!r.ok) {
          saveSession(null);
          setSession(null);
          return;
        }
        const data = await r.json();
        if (data?.user) {
          const next = { ...s, user: { ...s.user, ...data.user, credits: s.user.credits ?? 0 } };
          saveSession(next);
          setSession(next);
        }
      })
      .catch(() => {});
  }, []);

  const signup: AuthState["signup"] = async (email, password, full_name) => {
    if (!email.includes("@")) return { ok: false, error: "邮箱格式不正确" };
    if (password.length < 8) return { ok: false, error: "密码至少 8 位" };
    if (!full_name.trim()) return { ok: false, error: "请填写昵称" };
    const result = await authRequest("/api/v1/auth/signup", {
      email,
      password,
      full_name: full_name.trim(),
    });
    if (!result.ok) return result;
    saveSession(result.session);
    setSession(result.session);
    return { ok: true };
  };

  const login: AuthState["login"] = async (email, password) => {
    if (!email.includes("@") || !password) {
      return { ok: false, error: "请输入邮箱和密码" };
    }
    const result = await authRequest("/api/v1/auth/login", { email, password });
    if (!result.ok) return result;
    saveSession(result.session);
    setSession(result.session);
    return { ok: true };
  };

  const logout = () => {
    saveSession(null);
    setSession(null);
  };

  return (
    <AuthContext.Provider value={{ session, ready, signup, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
