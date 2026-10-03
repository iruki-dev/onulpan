import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { currentUser, isAdmin } from "@/lib/session";
import "./globals.css";

// 모든 페이지가 저장소를 읽는다. 빌드 때 미리 그리지 않는다.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.SITE_URL ?? "http://localhost:3000"),
  title: { default: "오늘판 — 하루 한 번, 오늘의 조간", template: "%s · 오늘판" },
  description: "여러 언론 보도를 AI가 종합해 쓰는 아침 조간. 사실은 모으고, 판단은 독자에게.",
  openGraph: { siteName: "오늘판", locale: "ko_KR", type: "website" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#fbf8f2" };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const user = await currentUser();
  return (
    <html lang="ko">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;800&family=Noto+Serif+KR:wght@700;900&display=swap"
        />
      </head>
      <body>
        <header className="site">
          <div className="wrap">
            <Link href="/" className="brand">오늘판</Link>
            <nav className="top">
              <Link href="/archive">지난 조간</Link>
              <Link href="/issues/weekly">이번 주 쟁점</Link>
              <Link href="/principles">편집 원칙</Link>
              {user ? (
                <>
                  <Link href="/settings">설정</Link>
                  {isAdmin(user) && <Link href="/admin/today">관리</Link>}
                </>
              ) : (
                <Link href="/login">로그인</Link>
              )}
            </nav>
          </div>
        </header>
        <main className="wrap">{children}</main>
        <footer className="site">
          <div className="wrap">
            <p>
              <Link href="/principles">편집 원칙</Link>
              <Link href="/principles#contact">기사배열책임자·청소년보호책임자</Link>
              <Link href="/founding">창립 멤버</Link>
              <Link href="/privacy">개인정보 처리방침</Link>
            </p>
            <p>오늘판의 모든 글은 AI가 여러 언론 보도를 종합해 씁니다. 글은 고치지 않고 덧붙입니다.</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
