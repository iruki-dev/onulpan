import "server-only";
import { createHash, randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { one, q } from "./db";
import { sign, verify } from "./tokens";

const COOKIE = "op_session";
const MAX_AGE = 60 * 60 * 24 * 90;

export type User = {
  id: string;
  email: string;
  provider: string;
  plan: "free" | "founding" | "premium";
  created_at: Date;
};

export async function currentUser(): Promise<User | null> {
  const jar = await cookies();
  const raw = verify("session", jar.get(COOKIE)?.value);
  if (!raw) return null;
  const [uid, exp] = raw.split("|");
  if (!uid || Number(exp) < Date.now() / 1000) return null;
  return one<User>("SELECT id, email, provider, plan, created_at FROM users WHERE id = $1 AND deleted_at IS NULL", [uid]);
}

export async function requireUser(next = "/"): Promise<User> {
  const u = await currentUser();
  if (!u) redirect(`/login?next=${encodeURIComponent(next)}`);
  return u;
}

export function isAdmin(u: User | null): boolean {
  if (!u) return false;
  const admins = (process.env.ADMIN_EMAILS ?? "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  return admins.includes(u.email.toLowerCase());
}

export async function requireAdmin(): Promise<User> {
  const u = await requireUser("/admin/today");
  if (!isAdmin(u)) redirect("/");
  return u;
}

export async function startSession(userId: string): Promise<void> {
  const jar = await cookies();
  const exp = Math.floor(Date.now() / 1000) + MAX_AGE;
  jar.set(COOKIE, sign("session", `${userId}|${exp}`), {
    httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge: MAX_AGE,
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(COOKIE);
}

/** 로그인 시 사용자 행을 만들거나 찾는다. 가입 경로(초대 코드, UTM)를 함께 남긴다 (채널별 CAC 측정). */
export async function upsertUser(email: string, provider: string): Promise<string> {
  const jar = await cookies();
  const invite = jar.get("op_invite")?.value ?? null;
  let utm: string | null = null;
  try {
    const raw = jar.get("op_utm")?.value;
    utm = raw ? JSON.stringify(JSON.parse(decodeURIComponent(raw))) : null;
  } catch {
    utm = null;
  }
  const normalized = email.trim().toLowerCase();
  const existing = await one<{ id: string }>("SELECT id FROM users WHERE email = $1 AND deleted_at IS NULL", [normalized]);
  if (existing) return existing.id;
  const validInvite = invite ? await one<{ code: string }>("SELECT code FROM invites WHERE code = $1", [invite]) : null;
  const row = await one<{ id: string }>(
    `INSERT INTO users (email, provider, invite_code, utm) VALUES ($1, $2, $3, $4)
     ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id`,
    [normalized, provider, validInvite?.code ?? null, utm],
  );
  await q("INSERT INTO user_prefs (user_id) VALUES ($1) ON CONFLICT DO NOTHING", [row!.id]);
  await q("INSERT INTO events (user_id, name, props) VALUES ($1, 'signup', $2)", [
    row!.id, JSON.stringify({ provider, invite: validInvite?.code ?? null }),
  ]);
  return row!.id;
}

export function randomToken(): string {
  return randomBytes(32).toString("base64url");
}

export function sha256(s: string): string {
  return createHash("sha256").update(s).digest("hex");
}

export function siteUrl(): string {
  return (process.env.SITE_URL ?? "http://localhost:3000").replace(/\/$/, "");
}

/** 오픈 리다이렉트 방지: 사이트 안의 경로만 허용 */
export function safeNext(next: string | null | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}
