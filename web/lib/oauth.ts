import "server-only";

// 카카오·구글 로그인 (authorization code). 키는 환경 변수로만 받는다.
export type Provider = "google" | "kakao";

export function providerConfig(p: string) {
  if (p === "google" && process.env.GOOGLE_CLIENT_ID) {
    return {
      authorize: "https://accounts.google.com/o/oauth2/v2/auth",
      token: "https://oauth2.googleapis.com/token",
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
      scope: "openid email",
    };
  }
  if (p === "kakao" && process.env.KAKAO_CLIENT_ID) {
    return {
      authorize: "https://kauth.kakao.com/oauth/authorize",
      token: "https://kauth.kakao.com/oauth/token",
      clientId: process.env.KAKAO_CLIENT_ID,
      clientSecret: process.env.KAKAO_CLIENT_SECRET ?? "",
      scope: "account_email",
    };
  }
  return null;
}

export function enabledProviders(): Provider[] {
  return (["kakao", "google"] as Provider[]).filter((p) => providerConfig(p));
}

export async function exchangeAndGetEmail(p: Provider, code: string, redirectUri: string): Promise<string | null> {
  const c = providerConfig(p)!;
  const body = new URLSearchParams({
    grant_type: "authorization_code", code, redirect_uri: redirectUri, client_id: c.clientId,
    ...(c.clientSecret ? { client_secret: c.clientSecret } : {}),
  });
  const tr = await fetch(c.token, { method: "POST", body, headers: { "content-type": "application/x-www-form-urlencoded" } });
  if (!tr.ok) return null;
  const tok = (await tr.json()) as { access_token?: string };
  if (!tok.access_token) return null;
  if (p === "google") {
    const r = await fetch("https://openidconnect.googleapis.com/v1/userinfo", { headers: { authorization: `Bearer ${tok.access_token}` } });
    const u = (await r.json()) as { email?: string; email_verified?: boolean };
    return u.email && u.email_verified ? u.email : null;
  }
  const r = await fetch("https://kapi.kakao.com/v2/user/me", { headers: { authorization: `Bearer ${tok.access_token}` } });
  const u = (await r.json()) as { kakao_account?: { email?: string; is_email_verified?: boolean } };
  return u.kakao_account?.email && u.kakao_account.is_email_verified ? u.kakao_account.email : null;
}
