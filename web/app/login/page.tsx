import Link from "next/link";
import { redirect } from "next/navigation";
import { Kakao } from "@/components/Icons";
import { enabledProviders } from "@/lib/oauth";
import { currentUser, safeNext } from "@/lib/session";

export const metadata = { title: "로그인" };

const ERRORS: Record<string, string> = {
  provider: "이 로그인 방식은 아직 준비 중이에요.",
  state: "로그인 요청이 만료됐어요. 다시 시도해 주세요.",
  email: "이메일 주소를 받지 못했어요. 이메일 제공 동의를 확인하거나 이메일로 로그인해 주세요.",
  email_format: "이메일 주소를 확인해 주세요.",
  expired: "로그인 링크가 만료됐거나 이미 쓰였어요.",
};

export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const next = safeNext(sp.next);
  if (await currentUser()) redirect(next);
  const providers = enabledProviders();
  const n = encodeURIComponent(next);
  return (
    <div className="page narrow">
      <div className="page-head" style={{ paddingTop: 40 }}>
        <h1 className="page-title">{sp.sent ? "메일함을 확인해 주세요" : "오늘판 시작하기"}</h1>
        <p className="page-sub">
          {sp.sent ? "로그인 링크를 보냈어요. 15분 안에 눌러 주세요." : sp.invited === "1" ? "초대받아 오셨군요. 반가워요." : "매일 아침 7시, 무료로 받아보세요."}
        </p>
      </div>
      {sp.error && <p className="notice error">{ERRORS[sp.error] ?? "로그인하지 못했어요."}</p>}
      {!sp.sent && (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {providers.includes("kakao") && <a className="btn kakao block" href={`/auth/kakao?next=${n}`}><Kakao />카카오로 시작하기</a>}
            {providers.includes("google") && <a className="btn secondary block" href={`/auth/google?next=${n}`}>구글로 시작하기</a>}
          </div>
          {providers.length > 0 && <div className="or"><span>또는</span></div>}
          <form action="/auth/email" method="post">
            <input type="hidden" name="next" value={next} />
            <label className="field">
              <span className="sr-only">이메일</span>
              <input className="input" type="email" name="email" required placeholder="이메일 주소" autoComplete="email" />
            </label>
            <button type="submit" className="btn block">{process.env.DEV_LOGIN === "1" ? "바로 로그인 (개발 모드)" : "로그인 링크 받기"}</button>
          </form>
        </>
      )}
      <p className="small muted" style={{ margin: "24px 0 40px", textAlign: "center", lineHeight: 1.6 }}>
        시작하면 <Link href="/privacy" className="u">개인정보 처리방침</Link>과 <Link href="/principles" className="u">편집 원칙</Link>에 동의하게 돼요.
      </p>
    </div>
  );
}
