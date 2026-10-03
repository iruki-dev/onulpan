import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { one, q } from "@/lib/db";
import { siteUrl } from "@/lib/session";

// 초대 링크 /invite/<코드>: 가입 경로를 기록한다 (채널별 CAC 측정의 기반)
export async function GET(_req: Request, ctx: { params: Promise<{ code: string }> }) {
  const { code } = await ctx.params;
  const inv = await one<{ code: string; channel: string }>("SELECT code, channel FROM invites WHERE code = $1", [code]);
  if (inv) {
    (await cookies()).set("op_invite", inv.code, { httpOnly: true, sameSite: "lax", maxAge: 60 * 60 * 24 * 30, path: "/" });
    await q("INSERT INTO events (name, props) VALUES ('invite_visit', $1)", [JSON.stringify({ code: inv.code, channel: inv.channel })]);
  }
  return NextResponse.redirect(`${siteUrl()}/login?invited=${inv ? 1 : 0}`);
}
