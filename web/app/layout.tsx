import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { Clock, Sliders } from "@/components/Icons";
import { TermSheet } from "@/components/TermSheet";
import { TopNav } from "@/components/TopNav";
import { currentUser, isAdmin } from "@/lib/session";
import "./globals.css";

// 모든 페이지가 저장소를 읽는다. 빌드 때 미리 그리지 않는다.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.SITE_URL ?? "http://localhost:3000"),
  title: { default: "오늘판 — 아침마다 한 부, 다 읽으면 끝나는 뉴스", template: "%s · 오늘판" },
  description: "여러 언론사의 보도를 모아 사실만 정리한 아침 조간.",
  openGraph: { siteName: "오늘판", locale: "ko_KR", type: "website" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#17191c" },
  ],
};

// 글자 크기 설정(가 버튼)을 첫 화면부터 적용한다
const bodySizeScript = `try{var s=localStorage.getItem("op_body_size");if(s)document.documentElement.style.setProperty("--body-size",s+"px")}catch(e){}`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const user = await currentUser();
  return (
    <html lang="ko">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Hahmlet:wght@600;700&family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap"
        />
        <script dangerouslySetInnerHTML={{ __html: bodySizeScript }} />
      </head>
      <body>
        <header className="app-header">
          <div className="inner">
            <Link href="/" className="wordmark">오늘판</Link>
            <TopNav />
            <div className="header-actions">
              {isAdmin(user) && <Link href="/admin/today" className="text-btn">관리</Link>}
              <Link href="/archive" className="icon-btn only-mobile-nav" aria-label="지난 조간"><Clock /></Link>
              {user ? (
                <Link href="/settings" className="icon-btn" aria-label="설정"><Sliders /></Link>
              ) : (
                <Link href="/login" className="text-btn">로그인</Link>
              )}
            </div>
          </div>
        </header>
        <main>{children}</main>
        <footer className="app-footer">
          <div className="inner">
            <span>AI가 여러 언론 보도를 종합해 씁니다</span>
            <Link href="/principles">편집 원칙</Link>
            <Link href="/privacy">개인정보 처리방침</Link>
            <Link href="/founding">창립 멤버</Link>
          </div>
        </footer>
        <TermSheet />
      </body>
    </html>
  );
}
