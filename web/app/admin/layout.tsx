import Link from "next/link";
import { requireAdmin } from "@/lib/session";

export const metadata = { title: "관리", robots: { index: false } };

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  await requireAdmin();
  return (
    <div className="admin">
      <nav className="sub" aria-label="관리">
        <Link href="/admin/today">오늘</Link>
        <Link href="/admin/drafts">초안</Link>
        <Link href="/admin/reports">제보·정정</Link>
        <Link href="/admin/images">이미지</Link>
        <Link href="/admin/outlets">매체</Link>
        <Link href="/admin/costs">비용</Link>
        <Link href="/admin/invites">초대 코드</Link>
      </nav>
      {children}
    </div>
  );
}
