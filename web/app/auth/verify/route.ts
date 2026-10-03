import { NextResponse } from "next/server";
import { one } from "@/lib/db";
import { safeNext, sha256, siteUrl, startSession, upsertUser } from "@/lib/session";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const token = url.searchParams.get("token") ?? "";
  const row = await one<{ email: string }>(
    `UPDATE login_tokens SET used_at = now()
     WHERE token_hash = $1 AND used_at IS NULL AND expires_at > now() RETURNING email`,
    [sha256(token)],
  );
  if (!row) return NextResponse.redirect(`${siteUrl()}/login?error=expired`);
  await startSession(await upsertUser(row.email, "email"));
  return NextResponse.redirect(`${siteUrl()}${safeNext(url.searchParams.get("next"))}`);
}
