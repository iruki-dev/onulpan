import { createHmac, timingSafeEqual } from "node:crypto";

// 워커(worker/mail/tokens.py)와 같은 형식: base64url(value) + "." + HMAC-SHA256(secret, purpose:value)[:32]
export function secret(): string {
  const s = process.env.ONULPAN_SECRET;
  if (!s && process.env.NODE_ENV === "production") throw new Error("ONULPAN_SECRET is required");
  return s ?? "dev-secret-change-me";
}

function mac(purpose: string, value: string): string {
  return createHmac("sha256", secret()).update(`${purpose}:${value}`).digest("hex").slice(0, 32);
}

export function sign(purpose: string, value: string): string {
  return `${Buffer.from(value).toString("base64url")}.${mac(purpose, value)}`;
}

export function verify(purpose: string, token: string | null | undefined): string | null {
  if (!token || !token.includes(".")) return null;
  const [v, m] = token.split(".", 2);
  let value: string;
  try {
    value = Buffer.from(v, "base64url").toString("utf8");
  } catch {
    return null;
  }
  const expected = Buffer.from(mac(purpose, value));
  const got = Buffer.from(m);
  return expected.length === got.length && timingSafeEqual(expected, got) ? value : null;
}
