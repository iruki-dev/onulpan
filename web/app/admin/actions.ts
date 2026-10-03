"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { enqueue, q } from "@/lib/db";
import { REJECT_REASONS } from "@/lib/labels";
import { requireAdmin } from "@/lib/session";

// 게시·반려·정정은 워커가 한다 (posts·decision_log는 워커만 쓴다). 웹은 작업을 넣는다.
export async function approveDraft(form: FormData) {
  await requireAdmin();
  await enqueue("publish_draft", { draft_id: Number(form.get("draft_id")), decision: "approved" });
  revalidatePath("/admin/today");
}

export async function rejectDraft(form: FormData) {
  await requireAdmin();
  const reason = String(form.get("reason"));
  if (!(reason in REJECT_REASONS)) throw new Error("bad reason");
  await enqueue("reject_draft", { draft_id: Number(form.get("draft_id")), reason, note: String(form.get("note") ?? "") || null });
  revalidatePath("/admin/today");
}

export async function publishCorrection(form: FormData) {
  const admin = await requireAdmin();
  const target = Number(form.get("target_seq"));
  const title = String(form.get("title") ?? "").trim();
  const body = String(form.get("body") ?? "").trim();
  const summary = String(form.get("summary") ?? "").trim();
  if (!target || !title || body.length < 20) redirect("/admin/reports?error=correction");
  await enqueue("publish_correction", {
    target_seq: target, title, summary: summary || title, body, author: admin.email,
    report_id: form.get("report_id") ? Number(form.get("report_id")) : null,
  });
  redirect("/admin/reports?queued=1");
}

export async function answerReport(form: FormData) {
  await requireAdmin();
  await q("UPDATE error_reports SET status = $2, answer = $3, answered_at = now() WHERE id = $1", [
    Number(form.get("id")), String(form.get("status")), String(form.get("answer") ?? ""),
  ]);
  revalidatePath("/admin/reports");
}

/** 언론사 요청으로 수집 대상에서 뺀다 (24시간 안에 처리). 이미 쓴 글의 출처 표시는 그대로 둔다. */
export async function excludeOutlet(form: FormData) {
  await requireAdmin();
  await q("UPDATE outlets SET active = false, excluded_at = now(), excluded_note = $2 WHERE id = $1", [
    Number(form.get("id")), String(form.get("note") ?? ""),
  ]);
  revalidatePath("/admin/outlets");
}

export async function createInvite(form: FormData) {
  await requireAdmin();
  const code = String(form.get("code") ?? "").trim().replace(/[^a-zA-Z0-9_-]/g, "");
  const channel = String(form.get("channel") ?? "").trim();
  if (!code || !channel) redirect("/admin/invites?error=1");
  await q("INSERT INTO invites (code, channel) VALUES ($1, $2) ON CONFLICT DO NOTHING", [code, channel]);
  revalidatePath("/admin/invites");
}
