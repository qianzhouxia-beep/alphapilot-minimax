// Server Component: 静态导出(output: export)需要 generateStaticParams。
// 当前仅为示例帖子 id 预生成页面；接入后端后建议改成 /cn/forum/post?id=xxx 的查询参数页（与 /cn/stock?symbol= 一致），
// 否则新帖子的详情页在静态导出下会 404。
import { MOCK_POSTS } from "@/lib/forum-mock";

export function generateStaticParams() {
  return MOCK_POSTS.map((p) => ({ id: p.id }));
}

export default function ForumPostLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
