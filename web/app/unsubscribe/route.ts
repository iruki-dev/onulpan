import { NextResponse } from "next/server";
import { q } from "@/lib/db";
import { siteUrl } from "@/lib/session";
import { verify } from "@/lib/tokens";

async function unsubscribe(token: string | null): Promise<boolean> {
  const uid = verify("unsub", token);
  if (!uid) return false;
  await q(
    `INSERT INTO user_prefs (user_id, email_enabled) VALUES ($1, false)
     ON CONFLICT (user_id) DO UPDATE SET email_enabled = false`,
    [uid],
  );
  await q("INSERT INTO events (user_id, name) VALUES ($1, 'unsubscribe')", [uid]);
  return true;
}

// 메일 앱의 원클릭 수신 거부 (RFC 8058): POST /unsubscribe?token=…
export async function POST(req: Request) {
  const ok = await unsubscribe(new URL(req.url).searchParams.get("token"));
  return new NextResponse(ok ? "unsubscribed" : "invalid token", { status: ok ? 200 : 400 });
}

// 메일 본문의 링크: 확인 화면 없이 바로 처리하고 결과를 보여준다
export async function GET(req: Request) {
  const ok = await unsubscribe(new URL(req.url).searchParams.get("token"));
  return NextResponse.redirect(`${siteUrl()}/unsubscribed?ok=${ok ? 1 : 0}`);
}
