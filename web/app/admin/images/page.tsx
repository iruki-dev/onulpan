import Link from "next/link";
import { q } from "@/lib/db";
import { LICENSES, RELATION_KO, TIER_KO } from "@/lib/labels";
import { kstDateTime } from "@/lib/time";
import {
  approveImage, findAnother, registerImage, rejectImage, resolveRequest, takeDownImage, updateImageText,
} from "./actions";

export const metadata = { title: "이미지 관리" };

type Item = {
  id: number; source_key: string; source_name: string; tier: string; status: string; found_by: string; hotlink: boolean;
  file_url: string | null; stored_path: string | null; origin_url: string; credit: string; alt: string; license: string;
  usage_terms: string | null; modifiable: boolean; subject: string | null; query: string | null; scope_slug: string | null;
  width: number | null; height: number | null; note: string | null; created_at: Date;
  checklist: { ok?: boolean; manual?: boolean; items?: { id: string; ok: boolean; label: string; note: string }[] };
  posts: { seq: number; title: string }[];
};

const ITEM_SQL = `SELECT i.*, s.name AS source_name, s.tier::text AS tier,
  COALESCE((SELECT json_agg(json_build_object('seq', p.seq, 'title', p.title) ORDER BY p.seq DESC)
            FROM post_images pi JOIN posts p ON p.seq = pi.post_seq WHERE pi.image_id = i.id AND pi.status = 'active'), '[]') AS posts
  FROM images i JOIN image_sources s ON s.key = i.source_key`;

const ERRORS: Record<string, string> = {
  checklist: "체크리스트 네 항목을 모두 확인해야 등록할 수 있어요.", url: "파일 주소(https)와 원본 페이지 주소를 확인해 주세요.",
  fields: "라이선스, 크레딧, 대체 텍스트는 꼭 필요해요.", source: "등록부에 없는 출처예요.",
  license: "이 출처에서 받지 않는 라이선스예요.", scope: "보도용 이미지는 다루는 소식(slug)을 지정해야 해요.",
  slug: "없는 slug예요.", duplicate: "이미 등록한 파일이에요.", resolve: "처리 방법과 회신 내용을 적어 주세요.",
  noreplacement: "승인 대기 중인 대체 이미지가 없어요. 직접 등록하거나 ‘다른 후보 찾기’를 먼저 해 주세요.",
  text: "크레딧과 대체 텍스트는 비울 수 없어요.",
};

function src(i: Item) {
  return i.hotlink && i.file_url ? i.file_url : i.stored_path ? `/img/${i.id}?admin=1` : null;
}

function Preview({ i }: { i: Item }) {
  const s = src(i);
  return (
    <div className="adm-preview">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {s ? <img src={s} alt={i.alt} /> : <span className="muted small">{i.status === "fetching" ? "받는 중…" : "파일 없음"}</span>}
    </div>
  );
}

function Checklist({ i }: { i: Item }) {
  const items = i.checklist.items ?? [];
  return (
    <ul className="adm-checks">
      {items.map((c) => (
        <li key={c.id} className={c.ok ? "ok" : "bad"}><span aria-hidden>{c.ok ? "✓" : "✕"}</span><b>{c.label}</b><span>{c.note}</span></li>
      ))}
      {i.checklist.manual && <li className="ok"><span aria-hidden>✓</span><b>관리자가 직접 확인</b><span /></li>}
    </ul>
  );
}

function Meta({ i }: { i: Item }) {
  return (
    <div className="adm-meta">
      <span className="pill">{TIER_KO[i.tier]}</span><span className="pill">{i.source_name}</span>
      <span className="pill">{LICENSES[i.license]?.label ?? i.license}</span>
      {!i.modifiable && <span className="pill">원본 유지</span>}
      {i.subject === "person" && <span className="pill bad">인물</span>}
      {i.scope_slug && <span className="pill">소식: {i.scope_slug}</span>}
      <a href={i.origin_url} target="_blank" rel="noopener" className="small">원본 페이지 ↗</a>
    </div>
  );
}

function Posts({ i }: { i: Item }) {
  if (!i.posts.length) return <p className="small muted">붙은 글 없음</p>;
  return (
    <p className="small">{i.posts.map((p) => <Link key={p.seq} href={`/p/${p.seq}`} style={{ marginRight: 12 }}>#{p.seq} {p.title}</Link>)}</p>
  );
}

function ItemCard({ i, tab, children }: { i: Item; tab: string; children?: React.ReactNode }) {
  return (
    <div className="card adm-image">
      <Preview i={i} />
      <div className="adm-body">
        <Meta i={i} />
        <form action={updateImageText} className="adm-text">
          <input type="hidden" name="id" value={i.id} /><input type="hidden" name="tab" value={tab} />
          <label>크레딧 (이미지 바로 아래 그대로)<input name="credit" defaultValue={i.credit} /></label>
          <label>대체 텍스트<input name="alt" defaultValue={i.alt} /></label>
          <button type="submit" className="ghost">표기 저장</button>
        </form>
        <Checklist i={i} />
        {i.usage_terms && <p className="small muted">이용 조건: {i.usage_terms}</p>}
        {i.query && <p className="small muted">검색어: {i.query} · {i.found_by === "auto" ? "자동 검색" : i.found_by === "graphic" ? "자체 그래픽" : "직접 등록"}</p>}
        {i.note && <p className="small error">{i.note}</p>}
        <Posts i={i} />
        {children}
      </div>
    </div>
  );
}

export default async function AdminImages({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const tab = sp.tab ?? "pending";
  const counts = (await q<{ k: string; n: number }>(
    `SELECT status AS k, count(*)::int AS n FROM images GROUP BY status
     UNION ALL SELECT 'requests', count(*)::int FROM image_requests WHERE status = 'open'`))
    .reduce<Record<string, number>>((a, r) => ({ ...a, [r.k]: r.n }), {});
  const tabs = [
    ["pending", `승인 대기 ${counts.pending ?? 0}`], ["active", `실린 이미지 ${counts.active ?? 0}`],
    ["requests", `권리자 요청 ${counts.requests ?? 0}`], ["down", "내림·반려"], ["new", "직접 등록"],
  ];
  return (
    <>
      <h1>이미지</h1>
      <p className="muted small">
        기준: docs/images.md · 출처와 분야별 순서: rules/image_sources.yaml. 자동으로 찾은 사진은 승인해야 실리고,
        자체 그래픽과 직접 등록한 이미지는 바로 실립니다.
      </p>
      <nav className="sub adm-tabs" aria-label="이미지 관리">
        {tabs.map(([k, l]) => <Link key={k} href={`/admin/images?tab=${k}`} aria-current={tab === k ? "page" : undefined}>{l}</Link>)}
      </nav>
      {sp.error && <p className="notice error">{ERRORS[sp.error] ?? "처리하지 못했어요."}</p>}
      {sp.registered && <p className="notice">등록했어요. 워커가 파일을 받아 체크리스트를 다시 확인한 뒤 실어요.</p>}
      {sp.resolved && <p className="notice">처리했어요. 요청자에게 회신을 보냅니다.</p>}
      {sp.queued && <p className="notice">다른 후보를 찾고 있어요. 찾으면 승인 대기에 올라와요.</p>}
      {tab === "pending" && <PendingTab />}
      {tab === "active" && <ActiveTab />}
      {tab === "requests" && <RequestsTab />}
      {tab === "down" && <DownTab />}
      {tab === "new" && <NewTab />}
    </>
  );
}

async function PendingTab() {
  const items = await q<Item>(`${ITEM_SQL} WHERE i.status IN ('pending','fetching') ORDER BY i.id DESC LIMIT 100`);
  if (!items.length) return <p className="muted">승인할 이미지가 없어요.</p>;
  return items.map((i) => (
    <ItemCard key={i.id} i={i} tab="pending">
      <div className="row">
        <form action={approveImage}><input type="hidden" name="id" value={i.id} /><button type="submit">승인</button></form>
        <form action={rejectImage} className="row">
          <input type="hidden" name="id" value={i.id} />
          <input name="note" placeholder="반려 이유 (선택)" style={{ width: 200 }} />
          <button type="submit" className="ghost">반려하고 다른 후보 찾기</button>
        </form>
      </div>
    </ItemCard>
  ));
}

async function ActiveTab() {
  const items = await q<Item>(`${ITEM_SQL} WHERE i.status = 'active' ORDER BY i.id DESC LIMIT 100`);
  if (!items.length) return <p className="muted">실린 이미지가 없어요.</p>;
  return items.map((i) => (
    <ItemCard key={i.id} i={i} tab="active">
      <div className="row">
        {i.posts[0] && (
          <form action={findAnother}>
            <input type="hidden" name="post_seq" value={i.posts[0].seq} /><input type="hidden" name="exclude" value={i.id} />
            <input type="hidden" name="tab" value="active" />
            <button type="submit" className="ghost">다른 후보 찾기</button>
          </form>
        )}
        <form action={takeDownImage} className="row">
          <input type="hidden" name="id" value={i.id} />
          <input name="note" placeholder="내리는 이유" style={{ width: 200 }} />
          <button type="submit" className="ghost">내리기</button>
        </form>
      </div>
    </ItemCard>
  ));
}

async function DownTab() {
  const items = await q<Item>(`${ITEM_SQL} WHERE i.status IN ('taken_down','rejected','failed') ORDER BY i.id DESC LIMIT 100`);
  if (!items.length) return <p className="muted">없어요.</p>;
  return items.map((i) => <ItemCard key={i.id} i={i} tab="down"><p className="small muted">상태: {i.status}</p></ItemCard>);
}

async function RequestsTab() {
  const reqs = await q<{
    id: number; image_id: number; name: string; email: string; relation: string; body: string; status: string;
    resolution: string | null; received_at: Date; acked_at: Date | null; resolved_at: Date | null; due: Date;
  }>(`SELECT r.*, r.received_at + interval '3 days' AS due FROM image_requests r
      ORDER BY (r.status = 'open') DESC, r.received_at DESC LIMIT 100`);
  if (!reqs.length) return <p className="muted">받은 요청이 없어요.</p>;
  const items = new Map((await q<Item>(`${ITEM_SQL} WHERE i.id = ANY($1::bigint[])`, [reqs.map((r) => r.image_id)])).map((i) => [i.id, i]));
  // 그 이미지를 쓰던 글의 대체 후보(승인 대기)
  const repl = await q<Item & { for_image: number }>(
    `${ITEM_SQL.replace("SELECT i.*", "SELECT DISTINCT ON (i.id) i.*, o.image_id AS for_image")}
     JOIN post_images o ON o.image_id = ANY($1::bigint[])
     JOIN post_images pi2 ON pi2.post_seq = o.post_seq AND pi2.image_id = i.id AND pi2.status = 'active'
     WHERE i.status = 'pending'`,
    [reqs.map((r) => r.image_id)]);
  const now = Date.now();
  return reqs.map((r) => {
    const i = items.get(r.image_id)!;
    const left = Math.ceil((new Date(r.due).getTime() - now) / 86400000);
    return (
      <div key={r.id} className="card" style={{ marginBottom: 16 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <strong>요청 #{r.id} · {RELATION_KO[r.relation]} · {r.name} &lt;{r.email}&gt;</strong>
          <span className={`pill ${r.status === "open" && left <= 0 ? "bad" : ""}`}>
            {r.status === "open" ? (left > 0 ? `회신 기한 D-${left}` : "회신 기한 지남") : { restored: "다시 실음", replaced: "교체", removed: "내린 채로" }[r.status]}
          </span>
        </div>
        <p className="small muted">받음 {kstDateTime(r.received_at)} · 이미지 내림 즉시 · 접수 회신 {r.acked_at ? kstDateTime(r.acked_at) : "보내는 중"}</p>
        <blockquote className="adm-quote">{r.body}</blockquote>
        {i && <ItemCard i={i} tab="requests" />}
        {repl.filter((x) => x.for_image === r.image_id).map((x) => (
          <div key={x.id}><p className="small"><b>대체 후보 (승인 대기)</b></p><ItemCard i={x} tab="requests" /></div>
        ))}
        {r.status === "open" ? (
          <form action={resolveRequest} className="adm-resolve">
            <input type="hidden" name="id" value={r.id} />
            <div className="row">
              <label className="row"><input type="radio" name="decision" value="restored" required /> 이용 근거를 제시하고 다시 싣기</label>
              <label className="row"><input type="radio" name="decision" value="replaced" /> 대체 이미지로 교체</label>
              <label className="row"><input type="radio" name="decision" value="removed" /> 내린 채로 두기</label>
            </div>
            <label>회신 내용 (요청자에게 그대로 보냅니다)
              <textarea name="resolution" rows={4} required placeholder="확인한 출처와 이용 조건, 또는 조치 내용을 적어 주세요." />
            </label>
            <button type="submit">처리하고 회신 보내기</button>
          </form>
        ) : (
          <p className="small">회신: {r.resolution} <span className="muted">({r.resolved_at ? kstDateTime(r.resolved_at) : ""})</span></p>
        )}
      </div>
    );
  });
}

async function NewTab() {
  const sources = await q<{ key: string; name: string; tier: string; licenses: string[]; scope_required: boolean; auto: boolean }>(
    "SELECT key, name, tier::text AS tier, licenses, scope_required, auto FROM image_sources WHERE active AND key <> 'own' ORDER BY ord");
  return (
    <form action={registerImage} className="card adm-new">
      <p className="small muted">
        기업 뉴스룸·프레스킷, 보도자료 배포 서비스, 공공누리 사진처럼 자동으로 찾지 않는 출처의 이미지를 등록합니다.
        보도용 이미지는 다루는 소식(slug)을 지정하면 그 소식의 글에만 붙습니다.
      </p>
      <label>출처
        <select name="source_key" required defaultValue="">
          <option value="" disabled>고르세요</option>
          {["press", "free"].map((t) => (
            <optgroup key={t} label={TIER_KO[t]}>
              {sources.filter((s) => s.tier === t).map((s) => (
                <option key={s.key} value={s.key}>{s.name} — {s.licenses.map((l) => LICENSES[l]?.label ?? l).join(", ")}{s.scope_required ? " · 소식 지정 필수" : ""}</option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>
      <div className="grid2">
        <label>이미지 파일 주소 (https)<input name="file_url" type="url" required placeholder="https://…/photo.jpg" /></label>
        <label>원본 페이지 (이용 조건이 적힌 곳)<input name="origin_url" type="url" required /></label>
        <label>라이선스
          <select name="license" required defaultValue="">
            <option value="" disabled>고르세요</option>
            {Object.entries(LICENSES).filter(([k]) => k !== "own").map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </label>
        <label>라이선스 주소 (CC BY-SA 등 링크가 필요한 경우)<input name="license_url" type="url" /></label>
        <label>지정 크레딧<input name="credit" required placeholder="사진: Intel Corporation / 사진: ○○시 제공 (공공누리 제1유형)" /></label>
        <label>작가·제공처<input name="author" /></label>
        <label>대체 텍스트<input name="alt" required placeholder="무엇이 보이는 사진인지 한 문장" /></label>
        <label>대상
          <select name="subject" defaultValue="object">
            {[["person", "인물"], ["place", "장소"], ["object", "사물"], ["event", "행사"], ["concept", "개념"], ["data", "자료"]].map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label>다루는 소식 slug (보도용 필수)<input name="scope_slug" placeholder="예: 누리전자-신제품" /></label>
        <label>바로 붙일 글 번호 (선택)<input name="attach_seq" inputMode="numeric" /></label>
      </div>
      <label>개별 이미지의 이용 조건 (원문 요약)<textarea name="usage_terms" rows={2} placeholder="예: Editorial use only. Credit: Intel Corporation" /></label>
      <fieldset className="adm-confirm">
        <legend>사용 전 체크리스트</legend>
        <label className="row"><input type="checkbox" name="c_source" /> 출처가 자유 이용 또는 보도용 제공 출처 목록에 있다</label>
        <label className="row"><input type="checkbox" name="c_license" /> 이 이미지 한 장의 라이선스와 이용 조건을 확인했다</label>
        <label className="row"><input type="checkbox" name="c_original" /> 원본 형태 그대로 싣는다 (변경 허용 라이선스가 아니면 자르지 않는다)</label>
        <label className="row"><input type="checkbox" name="c_credit" /> 출처가 지정한 크레딧을 그대로 적었다</label>
      </fieldset>
      <button type="submit">등록</button>
    </form>
  );
}
