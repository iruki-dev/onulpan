import { readFile } from "node:fs/promises";
import path from "node:path";
import { one } from "@/lib/db";
import { currentUser, isAdmin } from "@/lib/session";

// 저장된 표시용 파일을 내준다. 권리자 요청으로 내린 이미지는 즉시 404 (이메일에 박힌 주소도 함께 사라진다).
// 캐시는 짧게: 내린 뒤 길어야 10분 안에 어디서도 보이지 않게.
const ROOT = process.env.IMAGE_DIR ?? path.resolve(process.cwd(), "../var/images");

export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) return new Response("not found", { status: 404 });
  const row = await one<{ stored_path: string | null; mime: string | null; status: string; sha256: string | null }>(
    "SELECT stored_path, mime, status, sha256 FROM images WHERE id = $1",
    [Number(id)],
  );
  if (!row?.stored_path) return new Response("not found", { status: 404 });
  // 관리 화면은 승인 대기·내린 이미지도 본다 (?admin=1, 창업자 세션)
  const adminView = new URL(req.url).searchParams.has("admin");
  if (row.status !== "active") {
    const u = adminView ? await currentUser() : null;
    if (!u || !isAdmin(u)) return new Response("not found", { status: 404 });
  }
  const file = path.resolve(ROOT, row.stored_path);
  if (!file.startsWith(path.resolve(ROOT) + path.sep)) return new Response("not found", { status: 404 });
  const etag = `"${row.sha256}"`;
  if (req.headers.get("if-none-match") === etag && row.status === "active") return new Response(null, { status: 304 });
  try {
    const body = await readFile(file);
    return new Response(new Uint8Array(body), {
      headers: {
        "content-type": row.mime ?? "image/jpeg",
        "cache-control": row.status === "active" ? "public, max-age=600" : "private, no-store",
        etag,
        "x-content-type-options": "nosniff",
      },
    });
  } catch {
    return new Response("not found", { status: 404 });
  }
}
