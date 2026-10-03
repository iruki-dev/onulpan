import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { q } from "@/lib/db";
import { advanceCursor } from "@/lib/editions";
import { currentUser, randomToken } from "@/lib/session";

// 수집하는 이벤트 이름 (PRD의 이벤트 목록). 목록 밖의 이름은 버린다.
const ALLOWED = new Set([
  "page_view", "edition_open", "edition_complete", "link_click", "audio_interest", "share", "card_view",
]);

export async function POST(req: Request) {
  let data: { name?: string; props?: Record<string, unknown>; path?: string };
  try {
    data = await req.json();
  } catch {
    return new NextResponse(null, { status: 400 });
  }
  if (!data.name || !ALLOWED.has(data.name)) return new NextResponse(null, { status: 204 });
  const user = await currentUser();
  const jar = await cookies();
  let anon = jar.get("op_anon")?.value;
  if (!user && !anon) {
    anon = randomToken().slice(0, 22);
    jar.set("op_anon", anon, { httpOnly: true, sameSite: "lax", maxAge: 60 * 60 * 24 * 365, path: "/" });
  }
  const props = { ...(data.props ?? {}), path: String(data.path ?? "").slice(0, 200) };
  const json = JSON.stringify(props);
  if (json.length > 2000) return new NextResponse(null, { status: 413 });
  await q("INSERT INTO events (user_id, anon_id, name, props) VALUES ($1, $2, $3, $4)", [
    user?.id ?? null, user ? null : anon, data.name, json,
  ]);
  return new NextResponse(null, { status: 204 });
}
