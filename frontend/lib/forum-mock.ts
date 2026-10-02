// ═══════════════════════════════════════════════════════════════════════════
// 社区（论坛）— 第一版 UI 使用的【示例数据】
// ⚠️ 本文件中的所有帖子、回复、昵称、数字均为虚构的演示内容，不是真实用户发言。
// ⚠️ 本仓库没有论坛后端；接入后端时，把本文件中的 list/get 函数替换为 API 调用即可
//    （接口约定见 /workspace/forum-backend-spec.md）。
// ═══════════════════════════════════════════════════════════════════════════

export const FORUM_IS_MOCK = true;

export type SectionKey = "list" | "method" | "newbie" | "feedback";

export const SECTIONS: ReadonlyArray<{ key: SectionKey; label: string; desc: string }> = [
  { key: "list", label: "今日名单讨论", desc: "围绕当日名单、评分与资金阶段标签的交流与复盘" },
  { key: "method", label: "策略与方法", desc: "选股思路、指标理解、回测方法等研究性讨论" },
  { key: "newbie", label: "新手提问", desc: "入门概念、功能用法，欢迎提问" },
  { key: "feedback", label: "站务与反馈", desc: "产品建议、问题反馈、社区公告" },
];

export const SECTION_LABEL: Record<SectionKey, string> = Object.fromEntries(
  SECTIONS.map((s) => [s.key, s.label])
) as Record<SectionKey, string>;

/** 发帖限制（与后端规格保持一致，见 forum-backend-spec.md） */
export const FORUM_LIMITS = {
  titleMax: 60,
  bodyMax: 2000,
  replyMax: 500,
  dailyPostLimit: 5,
  minAccountAgeDays: 1,
  reportFoldThreshold: 3,
} as const;

export type StockRef = { name: string; code: string };

/** 示例用的股票名 → 代码映射（真实场景由后端按 $名称$ 解析） */
export const STOCK_MAP: Record<string, string> = {
  贵州茅台: "600519",
  宁德时代: "300750",
  京能热力: "002893",
  康华生物: "300841",
  捷成股份: "300182",
  平安银行: "000001",
  中国石油: "601857",
};

/** 官方账号显示名（站点名；接入后端后由官方账号的 nickname 提供） */
export const OFFICIAL_NAME = "AlphaPilot 官方";

/** 置顶范围：global = 全站置顶（所有板块与默认视图顶部）；section = 仅在所属板块置顶 */
export type PinScope = "global" | "section";

/** 保留昵称：普通用户不得使用含这些字样的昵称冒充官方（后端注册/改名时同样要校验） */
export const RESERVED_NICKNAME = /官方|alphapilot|站务|管理员|客服|admin/i;
export const safeNickname = (name?: string | null) => (name && !RESERVED_NICKNAME.test(name) ? name : "我");

export type ForumReply = {
  id: string;
  postId: string;
  author: string;
  /** 官方账号发表的回复（显示「官方」徽标） */
  isOfficial?: boolean;
  time: string; // ISO，显示时按字符串截取，避免静态导出的时区/水合不一致
  body: string;
  likes: number;
};

export type ForumPost = {
  id: string;
  section: SectionKey;
  title: string;
  body: string;
  author: string;
  time: string;
  replies: number;
  likes: number;
  stocks: StockRef[];
  /** 官方帖：由站点官方账号发布，只能由管理员创建（前端没有任何创建入口） */
  isOfficial?: boolean;
  /** 置顶范围；未置顶时为空。只能由管理员设置 */
  pinScope?: PinScope;
  /** 置顶排序，数字小的在前（同一范围内） */
  pinOrder?: number;
  /** 示例数据标记：true 表示虚构内容 */
  isExample: true;
};

const ex = true as const;

export const MOCK_POSTS: ForumPost[] = [
  {
    id: "1001",
    section: "list",
    title: "今天名单里「拉升」阶段的几只，大家怎么理解资金阶段标签？",
    body:
      "看了一下今天名单，$捷成股份$ 被标成「拉升确认」，$京能热力$ 是另一个阶段。想请教大家：资金阶段标签更适合当成“观察线索”还是“结论”？我自己的理解是只能当线索，要结合成交量和大盘环境再看。欢迎补充，也欢迎指出我理解不对的地方。",
    author: "示例用户·小林",
    time: "2026-10-02T21:30:00+08:00",
    replies: 6,
    likes: 18,
    stocks: [
      { name: "捷成股份", code: "300182" },
      { name: "京能热力", code: "002893" },
    ],
    isExample: ex,
  },
  {
    id: "1002",
    section: "list",
    title: "名单复盘：评分高的一定走得更好吗？",
    body:
      "我把最近几天名单里评分最高和评分靠后的各看了一遍，只是个人记录，样本很小，说明不了什么。想听听大家有没有更严谨的做法。提醒：评分是模型输出的相对排序，不是上涨概率。",
    author: "示例用户·阿杰",
    time: "2026-10-02T19:12:00+08:00",
    replies: 9,
    likes: 31,
    stocks: [],
    isExample: ex,
  },
  {
    id: "1003",
    section: "method",
    title: "回测里“持有天数”怎么选才不容易自欺欺人？",
    body:
      "回测工具里可以选持有天数。我的担心是：选了一个结果好看的区间，可能只是过拟合。大家一般怎么做样本外检查？另外回测不含全部真实交易摩擦，这点也想听听大家的处理方式。",
    author: "示例用户·量化小白",
    time: "2026-10-01T22:05:00+08:00",
    replies: 12,
    likes: 44,
    stocks: [],
    isExample: ex,
  },
  {
    id: "1004",
    section: "method",
    title: "资金流向指标和成交量比，哪个更适合做初筛？",
    body:
      "整理了一下我自己的笔记：资金流向受口径影响较大，成交量比相对直观。比如看 $宁德时代$ 这类大盘股时，资金流口径差异会更明显。想和大家交流一下各自的取舍，不涉及任何买卖建议。",
    author: "示例用户·Lin",
    time: "2026-09-30T20:40:00+08:00",
    replies: 7,
    likes: 23,
    stocks: [{ name: "宁德时代", code: "300750" }],
    isExample: ex,
  },
  {
    id: "1005",
    section: "newbie",
    title: "新手提问：A 股红涨绿跌，和海外软件颜色相反，怎么记？",
    body:
      "刚入门，经常看反。站里是红色表示上涨、绿色表示下跌对吧？有没有什么好记的方法？",
    author: "示例用户·新手小周",
    time: "2026-10-02T10:18:00+08:00",
    replies: 4,
    likes: 9,
    stocks: [],
    isExample: ex,
  },
  {
    id: "1006",
    section: "newbie",
    title: "“评分”和“上涨概率”是一回事吗？",
    body:
      "看到名单里有评分，是不是评分 80 就代表有 80% 的概率上涨？还是说只是排序用的？",
    author: "示例用户·小米",
    time: "2026-10-01T09:50:00+08:00",
    replies: 5,
    likes: 27,
    stocks: [],
    isExample: ex,
  },
  {
    id: "1007",
    section: "newbie",
    title: "收藏之后的 T+1 / T+2 / T+3 是怎么统计的？",
    body:
      "收藏了几只之后，收藏追踪页面会出现 T+1、T+2、T+3 的涨跌，是按收藏当天价格算的吗？比如我收藏了 $康华生物$ ，之后怎么看变化？",
    author: "示例用户·老王",
    time: "2026-09-29T15:22:00+08:00",
    replies: 3,
    likes: 6,
    stocks: [{ name: "康华生物", code: "300841" }],
    isExample: ex,
  },
  // ── 官方置顶帖（示例数据：内容仅用于演示，正式文案由运营撰写）──────────────
  {
    id: "1008",
    section: "feedback",
    title: "社区规则与发帖规范（示例）",
    body:
      "欢迎来到 AlphaPilot 社区（试运行）。为了让讨论保持清爽，请遵守以下规则：\n1. 禁止带单、喊单，禁止任何形式的收费荐股；\n2. 禁止拉群、导流，禁止留下微信 / QQ / 电话等联系方式及外部链接；\n3. 禁止承诺收益、保证盈利，禁止传播内幕消息；\n4. 理性、友善地讨论，不进行人身攻击。\n违规内容将被折叠或删除，情节严重者将限制发言。本站内容仅供学习与研究参考，不构成投资建议。",
    author: OFFICIAL_NAME,
    time: "2026-09-28T12:00:00+08:00",
    replies: 2,
    likes: 15,
    stocks: [],
    isOfficial: true,
    pinScope: "global",
    pinOrder: 1,
    isExample: ex,
  },
  {
    id: "1011",
    section: "newbie",
    title: "新手指南：如何看今日名单（示例）",
    body:
      "第一次来？可以按这个顺序看今日名单：\n1. 先看名单的更新时间和当天的市场状态；\n2. 评分是模型对名单内标的的相对排序，用来缩小关注范围；\n3. 资金阶段标签是观察线索，需要结合成交量、大盘环境自己判断；\n4. 看到感兴趣的标的，可以收藏后持续观察。\n名单仅供学习研究，不构成投资建议，也不代表对任何标的的买卖推荐。",
    author: OFFICIAL_NAME,
    time: "2026-09-28T12:30:00+08:00",
    replies: 5,
    likes: 36,
    stocks: [],
    isOfficial: true,
    pinScope: "global",
    pinOrder: 2,
    isExample: ex,
  },
  {
    id: "1012",
    section: "list",
    title: "评分与资金阶段说明：评分不是上涨概率（示例）",
    body:
      "评分是模型对名单内标的的相对排序，数值越高只表示在当日名单中的相对位置越靠前，不是上涨概率，也不是收益承诺。\n资金阶段是根据资金行为划分的观察标签，用来帮助理解资金动向，同样不是买卖信号。\n历史评估结果不代表未来表现，请独立判断并自行承担风险。",
    author: OFFICIAL_NAME,
    time: "2026-09-29T09:00:00+08:00",
    replies: 8,
    likes: 52,
    stocks: [],
    isOfficial: true,
    pinScope: "section",
    pinOrder: 1,
    isExample: ex,
  },
  {
    id: "1013",
    section: "feedback",
    title: "产品更新日志（示例）",
    body:
      "【示例日志，仅演示版式】\n· 新增「社区」：可浏览讨论、发帖、回复；\n· 个股页新增「讨论」区，展示与该股票相关的帖子；\n· 登录后可保存收藏、使用模拟盘。\n如有建议，欢迎在本板块反馈。",
    author: OFFICIAL_NAME,
    time: "2026-10-01T18:00:00+08:00",
    replies: 3,
    likes: 21,
    stocks: [],
    isOfficial: true,
    pinScope: "section",
    pinOrder: 1,
    isExample: ex,
  },
  {
    id: "1009",
    section: "feedback",
    title: "建议：个股页能不能加一个“相关讨论”入口",
    body: "希望在个股详情页直接看到该股票相关的讨论，比如 $贵州茅台$ 这种关注度高的。",
    author: "示例用户·阿鹏",
    time: "2026-09-30T08:31:00+08:00",
    replies: 3,
    likes: 12,
    stocks: [{ name: "贵州茅台", code: "600519" }],
    isExample: ex,
  },
  {
    id: "1010",
    section: "list",
    title: "关于 $京能热力$ 的资金流向，盘后数据怎么看更稳妥？",
    body:
      "盘后更新的资金流数据和盘中实时的不太一样，想问大家看资金阶段时用哪个口径。以下仅为个人学习记录，不构成任何建议。",
    author: "示例用户·Echo",
    time: "2026-10-02T18:20:00+08:00",
    replies: 2,
    likes: 5,
    stocks: [{ name: "京能热力", code: "002893" }],
    isExample: ex,
  },
];

const R = (
  id: string,
  postId: string,
  author: string,
  time: string,
  body: string,
  likes: number,
  isOfficial = false
): ForumReply => ({ id, postId, author, time, body, likes, ...(isOfficial ? { isOfficial: true } : {}) });

export const MOCK_REPLIES: ForumReply[] = [
  R("r0", "1008", OFFICIAL_NAME, "2026-09-28T12:10:00+08:00", "补充：发现违规内容请使用帖子下方的「举报」，累计多次举报的内容会被自动折叠并进入人工审核。", 6, true),
  R("r1", "1001", "示例用户·阿杰", "2026-10-02T21:48:00+08:00", "我也是当线索用，标签是模型根据资金行为分的阶段，不是买卖信号。", 7),
  R("r2", "1001", "示例用户·Echo", "2026-10-02T22:03:00+08:00", "同意。另外盘后和盘中的数据口径不同，看的时候注意更新时间。", 4),
  R("r3", "1001", OFFICIAL_NAME, "2026-10-02T22:20:00+08:00", "提醒：阶段标签与评分均为模型输出，仅供研究参考，不构成投资建议。", 11, true),
  R("r4", "1002", "示例用户·小林", "2026-10-02T19:40:00+08:00", "样本太小确实说明不了问题，建议拉长到几个月再看。", 3),
  R("r5", "1002", "示例用户·量化小白", "2026-10-02T20:05:00+08:00", "评分更像相对排序，而不是概率，这点官网也写了。", 6),
  R("r6", "1003", "示例用户·Lin", "2026-10-01T22:30:00+08:00", "可以把区间分成前后两段，前段调参、后段只验证，不回头改参数。", 9),
  R("r7", "1003", "示例用户·阿杰", "2026-10-01T23:10:00+08:00", "同意，另外别只看平均收益，也看看分布。", 2),
  R("r8", "1005", "示例用户·小米", "2026-10-02T10:40:00+08:00", "我的记法：红色像“火”，热、往上；绿色像“草”，往下。", 5),
  R("r9", "1006", OFFICIAL_NAME, "2026-10-01T10:15:00+08:00", "评分是模型对名单内标的的相对排序，不代表上涨概率，也不是收益承诺。", 14, true),
  R("r10", "1006", "示例用户·小周", "2026-10-01T10:50:00+08:00", "明白了，谢谢。", 1),
];

// ── 查询（接入后端时替换为 API 调用）────────────────────────────────────────

export type SortKey = "latest" | "hot";

const hotScore = (p: ForumPost) => p.likes * 2 + p.replies * 3;

const byTime = (a: ForumPost, b: ForumPost) => b.time.localeCompare(a.time);
const byPinOrder = (a: ForumPost, b: ForumPost) => (a.pinOrder ?? 999) - (b.pinOrder ?? 999) || byTime(a, b);

/**
 * 论坛首页列表：置顶区 + 普通区。
 * 规则：全站置顶（global）在所有板块都显示，排最前；其后是「所属板块」的板块置顶（section）；
 * 置顶帖不再重复出现在普通列表里；普通列表按 最新/热门 排序。
 */
export function listForum(opts: { section?: SectionKey; sort?: SortKey } = {}): { pinned: ForumPost[]; items: ForumPost[] } {
  const { section, sort = "latest" } = opts;
  const globals = MOCK_POSTS.filter((p) => p.pinScope === "global").sort(byPinOrder);
  const sections = MOCK_POSTS.filter((p) => p.pinScope === "section" && (!section || p.section === section)).sort(byPinOrder);
  const pinned = [...globals, ...sections];
  const pinnedIds = new Set(pinned.map((p) => p.id));
  const cmp = sort === "hot" ? (a: ForumPost, b: ForumPost) => hotScore(b) - hotScore(a) || byTime(a, b) : byTime;
  const items = MOCK_POSTS.filter((p) => !pinnedIds.has(p.id) && (section ? p.section === section : true)).sort(cmp);
  return { pinned, items };
}

/** 平铺列表（个股页「讨论」等不需要置顶区的场景）：按股票过滤，不做置顶 */
export function listPosts(opts: { section?: SectionKey; sort?: SortKey; symbol?: string } = {}): ForumPost[] {
  const { section, sort = "latest", symbol } = opts;
  let rows = MOCK_POSTS.filter((p) => (section ? p.section === section : true));
  if (symbol) rows = rows.filter((p) => p.stocks.some((s) => s.code === symbol));
  const cmp = sort === "hot" ? (a: ForumPost, b: ForumPost) => hotScore(b) - hotScore(a) || byTime(a, b) : byTime;
  return [...rows].sort(cmp);
}

export function getPost(id: string): ForumPost | undefined {
  return MOCK_POSTS.find((p) => p.id === id);
}

export function listReplies(postId: string): ForumReply[] {
  return MOCK_REPLIES.filter((r) => r.postId === postId).sort((a, b) => a.time.localeCompare(b.time));
}

// ── 展示工具 ───────────────────────────────────────────────────────────────

/** 当前上海时间的 ISO 字符串（仅用于示例发帖的时间戳） */
export function nowShanghaiIso(): string {
  return new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 19) + "+08:00";
}

/** "2026-10-02T21:30:00+08:00" → "10-02 21:30"（按字符串截取，保持上海时间且 SSR/CSR 一致） */
export function formatTime(iso: string): string {
  return `${iso.slice(5, 10)} ${iso.slice(11, 16)}`;
}

export function excerptOf(body: string, max = 90): string {
  const plain = body.replace(/\$([^$]+)\$/g, "$1").replace(/\s+/g, " ").trim();
  return plain.length > max ? plain.slice(0, max) + "…" : plain;
}

export function avatarInitial(name: string): string {
  const n = name.replace(/^示例(用户)?[·.]?/, "");
  return (n || name).trim().charAt(0).toUpperCase();
}

// ── 发帖前端提示用的检测（仅提示；真正拦截以后端为准）──────────────────────

const CONTACT_PATTERNS: Array<[RegExp, string]> = [
  [/(https?:\/\/|www\.)\S+/i, "链接"],
  [/[\w-]+\.(com|cn|net|cc|top|io|me|vip|xyz)\b/i, "网址"],
  [/(微信|vx|v信|wx|weixin|qq|扣扣|电话|手机号|telegram|tg)\s*[:：]?\s*[\w-]{4,}/i, "联系方式"],
  [/\b1[3-9]\d{9}\b/, "手机号"],
  [/(加群|拉群|进群|私聊|私信我|加我)/, "导流话术"],
];
const RULE_WORDS = ["带单", "喊单", "稳赚", "保证收益", "包赚", "内幕消息", "荐股收费", "收费荐股", "跟我买"];

export function checkContent(text: string): { blocked: string | null; hint: string | null } {
  for (const [re, name] of CONTACT_PATTERNS) {
    if (re.test(text)) return { blocked: `内容疑似包含${name}，社区禁止留联系方式或外链，请删除后再发布。`, hint: null };
  }
  const hit = RULE_WORDS.find((w) => text.includes(w));
  if (hit) return { blocked: `内容包含社区禁止的表述「${hit}」，请修改后再发布。`, hint: null };
  return { blocked: null, hint: null };
}
