"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { enqueue, q } from "@/lib/db";
import { LICENSES } from "@/lib/labels";
import { requireAdmin } from "@/lib/session";

const back = (tab: string, extra = "") => `/admin/images?tab=${tab}${extra}`;

/** 자동으로 찾은 이미지 승인: 이제부터 실린다. */
export async function approveImage(form: FormData) {
  await requireAdmin();
  await q("UPDATE images SET status = 'active', reviewed_at = now() WHERE id = $1 AND status = 'pending'", [Number(form.get("id"))]);
  revalidatePath("/admin/images");
}

/** 반려: 글과의 연결을 끊고, 그 글에 다른 후보를 찾는다 (반려한 이미지는 다시 고르지 않는다). */
export async function rejectImage(form: FormData) {
  await requireAdmin();
  const id = Number(form.get("id"));
  await q("UPDATE images SET status = 'rejected', reviewed_at = now(), note = $2 WHERE id = $1", [id, String(form.get("note") ?? "") || null]);
  const posts = await q<{ post_seq: number }>(
    `UPDATE post_images SET status = 'removed', removed_at = now(), removed_reason = 'rejected'
     WHERE image_id = $1 AND status = 'active' RETURNING post_seq`, [id]);
  for (const p of posts) await enqueue("find_image", { post_seq: p.post_seq, exclude: [id] });
  revalidatePath("/admin/images");
}

export async function updateImageText(form: FormData) {
  await requireAdmin();
  const credit = String(form.get("credit") ?? "").trim();
  const alt = String(form.get("alt") ?? "").trim();
  if (!credit || !alt) redirect(back(String(form.get("tab") ?? "pending"), "&error=text"));
  await q("UPDATE images SET credit = $2, alt = $3 WHERE id = $1", [Number(form.get("id")), credit, alt]);
  revalidatePath("/admin/images");
}

/** 관리자가 직접 내리기 (권리자 요청이 아닌 경우: 오류 발견 등) */
export async function takeDownImage(form: FormData) {
  await requireAdmin();
  await q("UPDATE images SET status = 'taken_down', taken_down_at = now(), note = $2 WHERE id = $1",
    [Number(form.get("id")), String(form.get("note") ?? "") || "관리자가 내림"]);
  revalidatePath("/admin/images");
}

export async function findAnother(form: FormData) {
  await requireAdmin();
  const seq = Number(form.get("post_seq"));
  const exclude = String(form.get("exclude") ?? "").split(",").map(Number).filter(Boolean);
  await enqueue("find_image", { post_seq: seq, exclude });
  redirect(back(String(form.get("tab") ?? "active"), "&queued=1"));
}

/**
 * 직접 등록: 보도용 제공(뉴스룸·프레스킷 등)과 공공누리처럼 자동 검색하지 않는 출처.
 * 체크리스트 네 항목을 사람이 확인해야 저장된다. 파일은 워커가 받아 저장하고 체크리스트를 다시 돌린다.
 */
export async function registerImage(form: FormData) {
  await requireAdmin();
  const v = (k: string) => String(form.get(k) ?? "").trim();
  const source = v("source_key"), license = v("license"), fileUrl = v("file_url"), origin = v("origin_url");
  const credit = v("credit"), alt = v("alt"), slug = v("scope_slug") || null;
  const attach = Number(v("attach_seq")) || null;
  const checks = ["c_source", "c_license", "c_original", "c_credit"].every((k) => form.get(k) === "on");
  const fail = (e: string) => redirect(back("new", `&error=${e}`));
  if (!checks) fail("checklist");
  if (!/^https:\/\//.test(fileUrl) || !/^https?:\/\//.test(origin)) fail("url");
  if (!(license in LICENSES) || !credit || !alt) fail("fields");
  const src = await q<{ licenses: string[]; scope_required: boolean; tier: string }>(
    "SELECT licenses, scope_required, tier::text AS tier FROM image_sources WHERE key = $1 AND active", [source]);
  if (!src.length) fail("source");
  if (!src[0].licenses.includes(license)) fail("license");
  if (src[0].scope_required && !slug) fail("scope");
  if (slug && !(await q("SELECT 1 FROM slugs WHERE slug = $1", [slug])).length) fail("slug");
  const checklist = {
    manual: true,
    items: [
      { id: "source", ok: true, label: "출처가 목록에 있음", note: "관리자 확인" },
      { id: "license", ok: true, label: "개별 이미지의 라이선스·이용 조건 확인", note: v("usage_terms") || LICENSES[license].label },
      { id: "original", ok: true, label: "원본 형태 유지", note: "관리자 확인" },
      { id: "credit", ok: true, label: "지정 크레딧을 이미지 바로 아래 표기", note: credit },
    ],
  };
  const [row] = await q<{ id: number }>(
    `INSERT INTO images (source_key, origin_url, file_url, alt, author, license, license_url, credit, usage_terms, scope_slug,
                         subject, checklist, status, found_by, title)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'fetching','admin',$13)
     ON CONFLICT (source_key, file_url) WHERE file_url IS NOT NULL DO NOTHING RETURNING id`,
    [source, origin, fileUrl, alt, v("author") || null, license, v("license_url") || null, credit, v("usage_terms") || null,
     slug, v("subject") || null, JSON.stringify(checklist), v("title") || null],
  );
  if (!row) fail("duplicate");
  await enqueue("fetch_image", { image_id: row.id, attach_seq: attach });
  redirect(back("active", "&registered=1"));
}

/**
 * 권리자 요청 처리 (가이드 ‘권리자 요청 대응’ 2·3): 이용 근거를 제시하고 다시 싣거나, 대체 이미지로 바꾸거나, 내린 채로 둔다.
 * 어느 쪽이든 회신 내용을 적어야 하고, 워커가 요청자에게 보낸다.
 */
export async function resolveRequest(form: FormData) {
  await requireAdmin();
  const id = Number(form.get("id"));
  const action = String(form.get("decision"));
  const resolution = String(form.get("resolution") ?? "").trim();
  if (!["restored", "replaced", "removed"].includes(action) || resolution.length < 5) redirect(back("requests", "&error=resolve"));
  const [req] = await q<{ image_id: number }>("SELECT image_id FROM image_requests WHERE id = $1", [id]);
  if (!req) redirect(back("requests"));
  let replacement: number | null = null;
  // 요청 이미지를 쓰던 글
  const posts = (await q<{ post_seq: number }>("SELECT DISTINCT post_seq FROM post_images WHERE image_id = $1", [req.image_id]))
    .map((r) => r.post_seq);
  if (action === "restored") {
    // 승인 대기 중이던 대체 후보를 떼고 원래 이미지를 다시 붙인다
    await q(
      `UPDATE post_images pi SET status = 'removed', removed_at = now(), removed_reason = 'original restored'
       FROM images i WHERE i.id = pi.image_id AND pi.status = 'active' AND i.status = 'pending' AND pi.post_seq = ANY($1::bigint[])`,
      [posts]);
    for (const seq of posts) {
      const active = await q("SELECT 1 FROM post_images WHERE post_seq = $1 AND role = 'lead' AND status = 'active'", [seq]);
      if (!active.length) await q("INSERT INTO post_images (post_seq, image_id) VALUES ($1, $2)", [seq, req.image_id]);
    }
    await q("UPDATE images SET status = 'active', taken_down_at = NULL WHERE id = $1", [req.image_id]);
  } else if (action === "replaced") {
    const rows = await q<{ image_id: number }>(
      `UPDATE images SET status = 'active', reviewed_at = now() WHERE id IN (
         SELECT pi.image_id FROM post_images pi JOIN images i ON i.id = pi.image_id
         WHERE pi.post_seq = ANY($1::bigint[]) AND pi.status = 'active' AND i.status = 'pending' AND i.id <> $2)
       RETURNING id AS image_id`, [posts, req.image_id]);
    if (!rows.length) redirect(back("requests", "&error=noreplacement"));
    replacement = rows[0].image_id;
  }
  await q("UPDATE image_requests SET status = $2, resolution = $3, resolved_at = now(), replacement_image_id = $4 WHERE id = $1",
    [id, action, resolution, replacement]);
  await enqueue("image_reply", { request_id: id });
  redirect(back("requests", "&resolved=1"));
}
