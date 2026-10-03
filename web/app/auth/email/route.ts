import { NextResponse } from "next/server";
import { enqueue, one, q } from "@/lib/db";
import { randomToken, safeNext, sha256, siteUrl, startSession, upsertUser } from "@/lib/session";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function POST(req: Request) {
  const form = await req.formData();
  const email = String(form.get("email") ?? "").trim().toLowerCase();
  const next = safeNext(String(form.get("next") ?? "/"));
  if (!EMAIL_RE.test(email) || email.length > 200) {
    return NextResponse.redirect(`${siteUrl()}/login?error=email_format`, 303);
  }
  // 개발 환경: 메일 없이 바로 로그인
  if (process.env.DEV_LOGIN === "1" && process.env.ONULPAN_ENV !== "production") {
    await startSession(await upsertUser(email, "email"));
    return NextResponse.redirect(`${siteUrl()}${next}`, 303);
  }
  // 같은 주소로 10분에 3번까지만
  const recent = await one<{ n: number }>(
    "SELECT count(*)::int AS n FROM login_tokens WHERE email = $1 AND expires_at > now() - interval '5 minutes'",
    [email],
  );
  if ((recent?.n ?? 0) < 3) {
    const token = randomToken();
    await q("INSERT INTO login_tokens (token_hash, email, expires_at) VALUES ($1, $2, now() + interval '15 minutes')", [
      sha256(token), email,
    ]);
    await enqueue("send_login_email", {
      email, url: `${siteUrl()}/auth/verify?token=${token}&next=${encodeURIComponent(next)}`,
    });
  }
  return NextResponse.redirect(`${siteUrl()}/login?sent=1`, 303);
}
