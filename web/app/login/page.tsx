import Link from "next/link";
import { redirect } from "next/navigation";
import { enabledProviders } from "@/lib/oauth";
import { currentUser, safeNext } from "@/lib/session";

export const metadata = { title: "로그인" };

const ERRORS: Record<string, string> = {
  provider: "이 로그인 방식은 아직 준비 중입니다.",
  state: "로그인 요청이 만료되었습니다. 다시 시도해 주세요.",
  email: "이메일 주소를 받지 못했습니다. 이메일 동의를 확인하거나 이메일로 로그인해 주세요.",
  email_format: "이메일 주소를 확인해 주세요.",
  expired: "로그인 링크가 만료되었거나 이미 사용되었습니다.",
};

export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const next = safeNext(sp.next);
  if (await currentUser()) redirect(next);
  const providers = enabledProviders();
  return (
    <>
      <h1>오늘판 받아보기</h1>
      <p>매일 아침 7시, 정해 둔 분량만큼의 조간을 이메일과 웹으로 보내드립니다. 무료입니다.</p>
      {sp.invited === "1" && <p className="notice">초대 링크로 오셨습니다. 반갑습니다.</p>}
      {sp.error && <p className="error">{ERRORS[sp.error] ?? "로그인하지 못했습니다."}</p>}
      {sp.sent ? (
        <p className="notice">로그인 링크를 이메일로 보냈습니다. 15분 안에 눌러 주세요.</p>
      ) : (
        <>
          <div className="actions">
            {providers.includes("kakao") && <a className="button" href={`/auth/kakao?next=${encodeURIComponent(next)}`}>카카오로 시작하기</a>}
            {providers.includes("google") && <a className="button ghost" href={`/auth/google?next=${encodeURIComponent(next)}`}>구글로 시작하기</a>}
          </div>
          <form action="/auth/email" method="post">
            <input type="hidden" name="next" value={next} />
            <label>이메일로 로그인 링크 받기<input type="email" name="email" required placeholder="you@example.com" autoComplete="email" /></label>
            <button type="submit">링크 받기</button>
            {process.env.DEV_LOGIN === "1" && <p className="muted small">개발 모드: 링크 없이 바로 로그인합니다.</p>}
          </form>
        </>
      )}
      <p className="muted small">
        가입하면 <Link href="/privacy">개인정보 처리방침</Link>과 <Link href="/principles">편집 원칙</Link>에 동의한 것으로 봅니다.
      </p>
    </>
  );
}
