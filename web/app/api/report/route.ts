import { NextResponse } from "next/server";
import { one, q } from "@/lib/db";
import { currentUser } from "@/lib/session";

// 오류 제보: 48시간 안에 확인하고 결과를 알린다.
export async function POST(req: Request) {
  const data = (await req.json().catch(() => ({}))) as { seq?: number; body?: string; contact?: string };
  const body = String(data.body ?? "").trim();
  if (body.length < 5 || body.length > 2000 || !Number.isInteger(Number(data.seq))) {
    return NextResponse.json({ ok: false }, { status: 400 });
  }
  const post = await one("SELECT seq FROM posts WHERE seq = $1", [Number(data.seq)]);
  if (!post) return NextResponse.json({ ok: false }, { status: 404 });
  const user = await currentUser();
  await q("INSERT INTO error_reports (post_seq, user_id, contact, body) VALUES ($1, $2, $3, $4)", [
    Number(data.seq), user?.id ?? null, String(data.contact ?? user?.email ?? "").slice(0, 200) || null, body,
  ]);
  return NextResponse.json({ ok: true });
}
