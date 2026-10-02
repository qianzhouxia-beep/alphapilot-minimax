// 社区（论坛）API 客户端：同源 /api/v1/cn/forum/*（本地开发连生产站，与 lib/cn-api.ts 一致）
// 字段与后端 forum_api.py（规格 v0.4）一致；错误统一转成 ForumApiError，用 describeError() 取中文提示。
// 可选环境变量 NEXT_PUBLIC_FORUM_API_BASE：联调时指向其他后端地址（默认不设置）。

const FORUM_BASE =
  process.env.NEXT_PUBLIC_FORUM_API_BASE ||
  (typeof window !== "undefined" && window.location.hostname === "localhost" ? "https://alphapilot.api-tokenmaster.com" : "");
const PREFIX = "/api/v1/cn/forum";

export const OFFICIAL_NAME = "AlphaPilot 官方";

// ── 常量（板块与限额；限额以 GET /meta 为准，meta 加载失败时用这里的默认值）──────────────

export type SectionKey = "list" | "method" | "newbie" | "feedback";
export type TabKey = SectionKey | "all";
export type SortKey = "latest" | "hot";

export const SECTIONS: ReadonlyArray<{ key: SectionKey; label: string; desc: string }> = [
  { key: "list", label: "今日名单讨论", desc: "围绕当日名单、评分与资金阶段标签的交流与复盘" },
  { key: "method", label: "策略与方法", desc: "选股思路、指标理解、回测方法等研究性讨论" },
  { key: "newbie", label: "新手提问", desc: "入门概念、功能用法，欢迎提问" },
  { key: "feedback", label: "站务与反馈", desc: "产品建议、问题反馈、社区公告" },
];

export const SECTION_LABEL: Record<SectionKey, string> = Object.fromEntries(
  SECTIONS.map((s) => [s.key, s.label])
) as Record<SectionKey, string>;

export const FORUM_LIMITS = {
  titleMax: 60,
  bodyMax: 2000,
  replyMax: 500,
  dailyPostLimit: 5,
  minAccountAgeDays: 1,
  reportFoldThreshold: 3,
} as const;

export const REPORT_REASONS: ReadonlyArray<{ code: string; label: string }> = [
  { code: "sales_pitch", label: "带单 / 喊单 / 荐股" },
  { code: "group_contact", label: "拉群 / 导流 / 联系方式" },
  { code: "ad_link", label: "广告 / 外链" },
  { code: "false_info", label: "承诺收益 / 虚假信息" },
  { code: "abuse", label: "人身攻击 / 骚扰" },
  { code: "other", label: "其他" },
];

// ── 类型 ────────────────────────────────────────────────────────────────

export type ForumAuthor = { id: string; nickname: string; avatar_initial: string; is_official: boolean };
export type ForumStock = { name: string; symbol: string; code: string };
export type PinScope = "none" | "global" | "section";
export type ViewerFlags = { liked: boolean; reported: boolean; favorited?: boolean; is_mine?: boolean };

export type ForumPost = {
  id: string;
  section: SectionKey;
  section_label: string;
  title: string;
  author: ForumAuthor;
  created_at: string;
  reply_count: number;
  like_count: number;
  is_official: boolean;
  pin_scope: PinScope;
  pin_order: number;
  status: "visible" | "folded" | "deleted";
  stocks: ForumStock[];
  viewer: ViewerFlags | null;
  fold_reason_label?: string;
  /** 列表接口返回 */
  excerpt?: string;
  /** 详情接口返回 */
  body?: string;
  /** 仅管理员请求会带 */
  admin?: { user_id: string; report_count: number; needs_review: boolean; fold_reason: string | null };
};

export type ForumReply = {
  id: string;
  post_id: string;
  author: ForumAuthor;
  body: string;
  created_at: string;
  like_count: number;
  is_official: boolean;
  status: "visible" | "folded" | "deleted";
  viewer: ViewerFlags | null;
  fold_reason_label?: string;
};

export type PostListResponse = { page: number; page_size: number; total: number; pinned: ForumPost[]; items: ForumPost[] };
export type ReplyListResponse = { page: number; page_size: number; total: number; items: ForumReply[] };
export type Quota = {
  posts_today: number;
  posts_limit: number;
  remaining_today: number;
  replies_today: number;
  replies_limit: number;
  reset_at: string;
  nickname: string;
  is_admin: boolean;
};
export type CreatePostResponse = { id: string; status: string; created_at: string; remaining_today: number; needs_review: boolean; post: ForumPost };

// ── 错误 ────────────────────────────────────────────────────────────────

export class ForumApiError extends Error {
  status: number;
  code: string;
  extra: Record<string, unknown>;
  constructor(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

export type ErrorAction = "login" | "nickname" | "retry" | null;

function waitText(sec: unknown): string {
  const n = Number(sec);
  if (!Number.isFinite(n) || n <= 0) return "稍后";
  return n >= 60 ? `${Math.ceil(n / 60)} 分钟后` : `${Math.ceil(n)} 秒后`;
}

/** 把任意错误转成给用户看的中文提示，并指出界面该做什么（登录 / 改昵称 / 重试） */
export function describeError(e: unknown): { message: string; action: ErrorAction; code: string } {
  if (!(e instanceof ForumApiError)) {
    return { message: "出了点问题，请稍后重试。", action: "retry", code: "UNKNOWN" };
  }
  const x = e.extra;
  const server = e.message;
  switch (e.code) {
    case "UNAUTHORIZED":
      return { message: "请先登录后再操作。", action: "login", code: e.code };
    case "NETWORK":
      return { message: "网络连接失败，请检查网络后重试。", action: "retry", code: e.code };
    case "SERVER":
      return { message: "社区服务暂时不可用，请稍后重试。", action: "retry", code: e.code };
    case "CONTENT_BLOCKED": {
      const byReason: Record<string, string> = {
        link: "内容里有链接或网址，社区不允许外链，请删除后再发布。",
        phone: "内容里有手机号或电话，为保护隐私不允许发布，请删除后再发布。",
        contact: "内容里有微信、QQ 等联系方式，社区不允许留联系方式，请删除后再发布。",
        promo: "内容含有带单、荐股或收益承诺类表述，社区不允许，请改为讨论方法和观点。",
        banned: "内容含有社区禁止的词语，请修改后再发布。",
      };
      return { message: byReason[String(x.reason)] || server || "内容含有社区不允许的信息，请修改后再发布。", action: null, code: e.code };
    }
    case "DAILY_POST_LIMIT":
      return { message: `今日发帖已达上限（每日最多 ${FORUM_LIMITS.dailyPostLimit} 帖），明天 0 点后可再发。`, action: null, code: e.code };
    case "DAILY_REPLY_LIMIT":
      return { message: "今日回复已达上限，明天 0 点后可再回复。", action: null, code: e.code };
    case "POST_COOLDOWN":
      return { message: `发帖太快了，请${waitText(x.retry_after)}再试。`, action: null, code: e.code };
    case "RATE_LIMITED":
      return { message: `操作太频繁，请${waitText(x.retry_after)}再试。`, action: null, code: e.code };
    case "NICKNAME_RESERVED":
      return { message: "你的昵称含有保留词（如官方、站务、管理员、客服），请先修改社区昵称后再发布。", action: "nickname", code: e.code };
    case "ACCOUNT_TOO_NEW":
      return { message: `账号注册满 ${FORUM_LIMITS.minAccountAgeDays} 天后才能发帖和回复，请明天再来。`, action: null, code: e.code };
    case "FORUM_MUTED":
      return { message: "你已被暂时禁言，暂时不能发帖或回复。", action: null, code: e.code };
    case "FORUM_BANNED":
      return { message: "你的账号已被社区限制发言。", action: null, code: e.code };
    case "PHONE_REQUIRED":
      return { message: "发帖前需要先绑定手机号。", action: null, code: e.code };
    case "DUPLICATE_POST":
      return { message: "检测到重复内容，请不要重复发布相同的帖子。", action: null, code: e.code };
    case "DUPLICATE_REPLY":
      return { message: "请不要重复发送相同的回复。", action: null, code: e.code };
    case "VALIDATION_ERROR":
      return { message: server || "填写的内容不符合要求，请检查后重试。", action: null, code: e.code };
    case "FIELD_NOT_ALLOWED":
      return { message: "提交的内容包含不允许的字段，请刷新页面后重试。", action: null, code: e.code };
    case "POST_CLOSED":
      return { message: "该内容已被折叠或关闭，无法继续操作。", action: null, code: e.code };
    case "POST_NOT_FOUND":
    case "NOT_FOUND":
    case "REPLY_NOT_FOUND":
      return { message: "内容不存在，可能已被删除。", action: null, code: e.code };
    case "ALREADY_REPORTED":
      return { message: "你已经举报过这条内容了，我们会尽快处理。", action: null, code: e.code };
    case "CANNOT_REPORT_SELF":
      return { message: "不能举报自己的内容。", action: null, code: e.code };
    case "FORBIDDEN":
      return { message: "你没有权限执行这个操作。", action: null, code: e.code };
    case "ADMIN_ONLY":
      return { message: "只有管理员可以执行这个操作。", action: null, code: e.code };
    case "PIN_LIMIT_EXCEEDED":
      return { message: "置顶数量已达上限，请先取消一条置顶。", action: null, code: e.code };
    default:
      return { message: server || "操作失败，请稍后重试。", action: e.status >= 500 ? "retry" : null, code: e.code };
  }
}

// ── 请求 ────────────────────────────────────────────────────────────────

function readToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("alphapilot_session");
    return raw ? (JSON.parse(raw) as { token?: string }).token || null : null;
  } catch {
    return null;
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = readToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${FORUM_BASE}${PREFIX}${path}`, {
      method,
      headers,
      cache: "no-store",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ForumApiError(0, "NETWORK", "network error");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text().catch(() => "");
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (res.ok) return data as T;
  const d = (data || {}) as { error?: unknown; detail?: unknown };
  // 论坛错误：{"error":{"code","message",...}}；登录依赖的 401：{"detail":"..."}；网关 502：{"error":"Backend unreachable"}
  if (d.error && typeof d.error === "object") {
    const { code, message, ...extra } = d.error as { code?: string; message?: string } & Record<string, unknown>;
    throw new ForumApiError(res.status, code || `HTTP_${res.status}`, message || "", extra);
  }
  if (res.status === 401) throw new ForumApiError(401, "UNAUTHORIZED", typeof d.detail === "string" ? d.detail : "");
  if (res.status >= 500) throw new ForumApiError(res.status, "SERVER", typeof d.error === "string" ? d.error : "");
  throw new ForumApiError(res.status, `HTTP_${res.status}`, typeof d.detail === "string" ? d.detail : "");
}

const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

const rid = (id: string) => encodeURIComponent(id);

// ── 公开读取 ────────────────────────────────────────────────────────────

export const getMeta = () =>
  call<{ sections: { key: SectionKey; label: string }[]; official_name: string; limits: Record<string, number> }>("GET", "/meta");

export const listPosts = (o: { section?: TabKey; sort?: SortKey; symbol?: string; page?: number; pageSize?: number } = {}) =>
  call<PostListResponse>("GET", `/posts${qs({ section: o.section ?? "all", sort: o.sort ?? "latest", symbol: o.symbol, page: o.page ?? 1, page_size: o.pageSize ?? 20 })}`);

export const getPost = (id: string, expand = false) => call<ForumPost>("GET", `/posts/${rid(id)}${qs({ expand: expand ? 1 : undefined })}`);

export const listReplies = (id: string, o: { page?: number; pageSize?: number; expand?: boolean } = {}) =>
  call<ReplyListResponse>("GET", `/posts/${rid(id)}/replies${qs({ page: o.page ?? 1, page_size: o.pageSize ?? 50, expand: o.expand ? 1 : undefined })}`);

// ── 登录后 ──────────────────────────────────────────────────────────────

export const getQuota = () => call<Quota>("GET", "/me/quota");
export const setNickname = (nickname: string) => call<{ nickname: string }>("PUT", "/me/profile", { nickname });

export const createPost = (b: { section: SectionKey; title: string; body: string }) => call<CreatePostResponse>("POST", "/posts", b);
export const createReply = (postId: string, body: string) =>
  call<{ id: string; reply: ForumReply; needs_review: boolean }>("POST", `/posts/${rid(postId)}/replies`, { body });

export const likePost = (id: string, on: boolean) => call<{ liked: boolean; like_count: number }>(on ? "PUT" : "DELETE", `/posts/${rid(id)}/like`);
export const likeReply = (id: string, on: boolean) => call<{ liked: boolean; like_count: number }>(on ? "PUT" : "DELETE", `/replies/${rid(id)}/like`);
export const favoritePost = (id: string, on: boolean) => call<{ favorited: boolean }>(on ? "PUT" : "DELETE", `/posts/${rid(id)}/favorite`);
export const reportContent = (b: { target_type: "post" | "reply"; target_id: string; reason: string; detail?: string }) =>
  call<{ id: number; status: string; folded: boolean }>("POST", "/reports", b);
export const deletePost = (id: string) => call<void>("DELETE", `/posts/${rid(id)}`);
export const deleteReply = (id: string) => call<void>("DELETE", `/replies/${rid(id)}`);

// ── 管理员（后端 403 ADMIN_ONLY 兜底；前端只对 quota.is_admin 显示入口）────────

export const adminPin = (id: string, scope: "global" | "section") =>
  call<{ id: string; pin_scope: PinScope; pin_order: number }>("PUT", `/admin/posts/${rid(id)}/pin`, { pin_scope: scope });
export const adminUnpin = (id: string) => call<{ id: string; pin_scope: PinScope }>("DELETE", `/admin/posts/${rid(id)}/pin`);
export const adminSetStatus = (id: string, action: "fold" | "unfold" | "delete" | "restore") =>
  call<{ id: string; status: string }>("POST", `/admin/posts/${rid(id)}/${action}`);
export const adminCreateOfficial = (b: { section: SectionKey; title: string; body: string; pin_scope: PinScope }) =>
  call<{ id: string }>("POST", "/admin/official-posts", b);
export const adminOfficialReply = (postId: string, body: string) =>
  call<{ id: string; reply: ForumReply }>("POST", `/admin/posts/${rid(postId)}/replies`, { body });

// ── 展示工具 ────────────────────────────────────────────────────────────

/** 帖子详情页地址（静态导出下用查询参数页，不能用 /cn/forum/[id]） */
export const postHref = (id: string) => `/cn/forum/post/?id=${encodeURIComponent(id)}`;

/** "2026-10-02T21:30:00+08:00" -> "10-02 21:30"（按字符串截取，保持上海时间，SSR/CSR 一致） */
export function formatTime(iso: string): string {
  return `${iso.slice(5, 10)} ${iso.slice(11, 16)}`;
}

export const stripMarks = (s: string) => s.replace(/\$([^$]+)\$/g, "$1");

// ── 发帖输入提示（只是友好提醒，真正的拦截以服务器为准）──────────────────────

const HINT_PATTERNS: Array<[RegExp, string]> = [
  [/(https?:\/\/|www\.)\S+/i, "链接"],
  [/[\w-]+\.(com|cn|net|cc|top|io|me|vip|xyz)\b/i, "网址"],
  [/(微信|vx|v信|wx|weixin|qq|扣扣|电话|手机号|telegram|tg)\s*[:：]?\s*[\w-]{4,}/i, "联系方式"],
  [/\b1[3-9]\d{9}\b/, "手机号"],
  [/(加群|拉群|进群|私聊|私信我|加我)/, "导流话术"],
  [/(带单|喊单|稳赚|保本|包赚|保证收益|内幕消息|收费荐股|跟我买)/, "荐股或收益承诺类表述"],
];

export function contentHint(text: string): string | null {
  for (const [re, name] of HINT_PATTERNS) {
    if (re.test(text)) return `内容疑似包含${name}，提交后很可能被拒绝，建议先删除。`;
  }
  return null;
}
