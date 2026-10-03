import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { exchangeAndGetEmail, providerConfig, type Provider } from "@/lib/oauth";
import { safeNext, siteUrl, startSession, upsertUser } from "@/lib/session";

export async function GET(req: Request, ctx: { params: Promise<{ provider: string }> }) {
  const { provider } = await ctx.params;
  if (!providerConfig(provider)) return NextResponse.redirect(`${siteUrl()}/login?error=provider`);
  const url = new URL(req.url);
  const jar = await cookies();
  const [state, next] = (jar.get("op_oauth")?.value ?? "").split("|");
  jar.delete("op_oauth");
  const code = url.searchParams.get("code");
  if (!code || !state || url.searchParams.get("state") !== state) {
    return NextResponse.redirect(`${siteUrl()}/login?error=state`);
  }
  const email = await exchangeAndGetEmail(provider as Provider, code, `${siteUrl()}/auth/${provider}/callback`);
  if (!email) return NextResponse.redirect(`${siteUrl()}/login?error=email`);
  await startSession(await upsertUser(email, provider));
  return NextResponse.redirect(`${siteUrl()}${safeNext(next)}`);
}
