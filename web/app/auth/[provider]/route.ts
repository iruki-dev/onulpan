import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { providerConfig } from "@/lib/oauth";
import { randomToken, safeNext, siteUrl } from "@/lib/session";

export async function GET(req: Request, ctx: { params: Promise<{ provider: string }> }) {
  const { provider } = await ctx.params;
  const c = providerConfig(provider);
  if (!c) return NextResponse.redirect(`${siteUrl()}/login?error=provider`);
  const state = randomToken();
  const next = safeNext(new URL(req.url).searchParams.get("next"));
  (await cookies()).set("op_oauth", `${state}|${next}`, { httpOnly: true, sameSite: "lax", maxAge: 600, path: "/" });
  const url = new URL(c.authorize);
  url.searchParams.set("client_id", c.clientId);
  url.searchParams.set("redirect_uri", `${siteUrl()}/auth/${provider}/callback`);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", c.scope);
  url.searchParams.set("state", state);
  return NextResponse.redirect(url.toString());
}
