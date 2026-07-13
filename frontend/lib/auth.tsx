"use client";

/**
 * Mock auth (M2 2026-06-05 — Boss pick A: 砍 M3 后端,前端 mock 登录态)
 *
 * - 存 localStorage (key: alphapilot_session)
 * - 跨页面共享:AuthProvider (React Context)
 * - 不依赖后端 8002 /api/auth/* (死路,M2 stub 替代)
 * - W3 老板拍 Stripe/账号体系后再接真后端
 */

import { createContext, useContext, useEffect, useState } from "react";

export type MockUser = {
  id: string;
  email: string;
  full_name: string;
  plan: "free" | "pro" | "elite";
  credits: number;  // W6: 用户余额
  created_at: string;
};

type Session = {
  token: string; // mock JWT (not real)
  user: MockUser;
};

type AuthState = {
  session: Session | null;
  signup: (email: string, password: string, full_name: string) => Promise<{ ok: boolean; error?: string }>;
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => void;
};

const STORAGE_KEY = "alphapilot_session";
const AuthContext = createContext<AuthState | null>(null);

function makeMockToken(email: string): string {
  // base64 trick: looks like a JWT but isn't signed
  const header = btoa(JSON.stringify({ alg: "none", typ: "JWT" }));
  const payload = btoa(JSON.stringify({ sub: email, iat: Date.now(), mock: true }));
  return `${header}.${payload}.mock_signature_${Date.now()}`;
}

function loadSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Session;
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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    setSession(loadSession());
  }, []);

  const signup: AuthState["signup"] = async (email, password, full_name) => {
    if (!email.includes("@")) return { ok: false, error: "Invalid email" };
    if (password.length < 8) return { ok: false, error: "Password must be 8+ chars" };
    if (!full_name.trim()) return { ok: false, error: "Full name required" };

    const user: MockUser = {
      id: `mock_${Date.now()}`,
      email: email.toLowerCase(),
      full_name: full_name.trim(),
      plan: "free",
      credits: 0,  // W6: 默认 0 credits
      created_at: new Date().toISOString(),
    };
    const newSession: Session = { token: makeMockToken(email), user };
    saveSession(newSession);
    setSession(newSession);
    return { ok: true };
  };

  const login: AuthState["login"] = async (email, password) => {
    if (!email.includes("@") || !password) {
      return { ok: false, error: "Invalid email or password" };
    }
    // Mock: any non-empty email/password works
    const user: MockUser = {
      id: `mock_${Date.now()}`,
      email: email.toLowerCase(),
      full_name: email.split("@")[0],
      plan: "free",
      credits: 0,  // W6: 默认 0 credits
      created_at: new Date().toISOString(),
    };
    const newSession: Session = { token: makeMockToken(email), user };
    saveSession(newSession);
    setSession(newSession);
    return { ok: true };
  };

  const logout = () => {
    saveSession(null);
    setSession(null);
  };

  return (
    <AuthContext.Provider value={{ session, signup, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
