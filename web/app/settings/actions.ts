"use server";
import { redirect } from "next/navigation";
import { enqueue, q } from "@/lib/db";
import { SECTIONS } from "@/lib/labels";
import { endSession, requireUser } from "@/lib/session";

const WEIGHT: Record<string, number> = { more: 1.3, normal: 1.0, less: 0.7 };

export async function savePrefs(form: FormData) {
  const user = await requireUser("/settings");
  const preset = String(form.get("preset"));
  if (!["short", "standard", "long"].includes(preset)) throw new Error("bad preset");
  const weights: Record<string, number> = {};
  for (const sec of SECTIONS) {
    const w = WEIGHT[String(form.get(`w_${sec}`) ?? "normal")] ?? 1.0;
    if (w !== 1.0) weights[sec] = w;
  }
  const hour = Math.min(10, Math.max(7, Number(form.get("delivery_hour") ?? 7)));
  const emailEnabled = form.get("email_enabled") === "on";
  let niche: string[] = [];
  if (user.plan !== "free") {
    const wanted = String(form.get("niche_topics") ?? "")
      .split(",").map((s) => s.trim().replaceAll(" ", "-")).filter(Boolean).slice(0, 5);
    if (wanted.length) {
      const rows = await q<{ slug: string }>("SELECT slug FROM slugs WHERE slug = ANY($1::text[])", [wanted]);
      const ok = new Set(rows.map((r) => r.slug));
      niche = wanted.filter((w) => ok.has(w));
    }
  }
  await q(
    `INSERT INTO user_prefs (user_id, preset, section_weights, niche_topics, delivery_hour, email_enabled)
     VALUES ($1, $2, $3, $4, $5, $6)
     ON CONFLICT (user_id) DO UPDATE SET preset = EXCLUDED.preset, section_weights = EXCLUDED.section_weights,
       niche_topics = EXCLUDED.niche_topics, delivery_hour = EXCLUDED.delivery_hour, email_enabled = EXCLUDED.email_enabled`,
    [user.id, preset, JSON.stringify(weights), niche, hour, emailEnabled],
  );
  await q("UPDATE users SET marketing_opt_in = $2 WHERE id = $1", [user.id, form.get("marketing_opt_in") === "on"]);
  if (emailEnabled) await q("DELETE FROM email_suppressions WHERE email = $1 AND reason = 'unsubscribe'", [user.email]);
  await q("INSERT INTO events (user_id, name, props) VALUES ($1, 'settings_saved', $2)", [
    user.id, JSON.stringify({ preset, weights, hour }),
  ]);
  // 설정을 바꾸면 워커에 즉시 재조립 작업을 넣는다 (수 초 이내). 웹은 편집기를 갖지 않는다.
  await enqueue("assemble_edition", { user_id: user.id });
  redirect("/settings?saved=1");
}

export async function logout() {
  await endSession();
  redirect("/");
}

/** 탈퇴: 개인정보를 파기한다. 추가 전용인 editions 기록은 식별자만 남고 이메일과 연결이 끊긴다. */
export async function deleteAccount(form: FormData) {
  const user = await requireUser("/settings");
  if (form.get("confirm") !== "탈퇴") redirect("/settings?delete=confirm");
  await q("DELETE FROM user_prefs WHERE user_id = $1", [user.id]);
  await q("DELETE FROM reading_cursors WHERE user_id = $1", [user.id]);
  await q("UPDATE events SET user_id = NULL, anon_id = NULL WHERE user_id = $1", [user.id]);
  await q(
    `UPDATE users SET email = 'deleted+' || id || '@invalid', utm = NULL, invite_code = NULL,
       marketing_opt_in = false, deleted_at = now() WHERE id = $1`,
    [user.id],
  );
  await endSession();
  redirect("/?bye=1");
}
