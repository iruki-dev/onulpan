"use server";
import { redirect } from "next/navigation";
import { enqueue, q } from "@/lib/db";
import { RELATION_KO } from "@/lib/labels";

/**
 * 권리자 요청: 받으면 바로 내린다 (가이드 ‘권리자 요청 대응’ 1).
 * 내리기는 웹이 이 자리에서 하고, 접수 회신·알림·대체 후보 찾기는 워커가 한다.
 */
export async function submitImageRequest(form: FormData) {
  const id = Number(form.get("image_id"));
  const name = String(form.get("name") ?? "").trim().slice(0, 80);
  const email = String(form.get("email") ?? "").trim().slice(0, 200);
  const relation = String(form.get("relation") ?? "");
  const body = String(form.get("body") ?? "").trim().slice(0, 4000);
  const back = `/images/request?id=${id}`;
  if (!Number.isInteger(id) || id <= 0) redirect("/images/request?error=image");
  if (!name || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) redirect(`${back}&error=contact`);
  if (!(relation in RELATION_KO)) redirect(`${back}&error=relation`);
  if (body.length < 5) redirect(`${back}&error=body`);
  const img = await q<{ id: number }>("SELECT id FROM images WHERE id = $1", [id]);
  if (!img.length) redirect("/images/request?error=image");

  const [req] = await q<{ id: number }>(
    "INSERT INTO image_requests (image_id, name, email, relation, body) VALUES ($1,$2,$3,$4,$5) RETURNING id",
    [id, name, email, relation, body],
  );
  await q(
    "UPDATE images SET status = 'taken_down', taken_down_at = COALESCE(taken_down_at, now()) WHERE id = $1 AND status IN ('active','pending')",
    [id],
  );
  await enqueue("image_request", { request_id: req.id });
  await q("INSERT INTO events (name, props) VALUES ('image_request', $1)", [JSON.stringify({ image_id: id, relation })]);
  redirect(`${back}&sent=1`);
}
