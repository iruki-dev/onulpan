import Link from "next/link";
import { Chevron } from "@/components/Icons";
import { q } from "@/lib/db";
import { PRESET_KO } from "@/lib/labels";
import { currentUser } from "@/lib/session";
import { kstDateLabel } from "@/lib/time";

export const metadata = { title: "지난 조간" };

export default async function ArchivePage() {
  const user = await currentUser();
  const mine = user
    ? await q<{ id: number; edition_date: string; preset: string }>(
        `SELECT DISTINCT ON (edition_date) id, edition_date, preset FROM editions WHERE user_id = $1
         ORDER BY edition_date DESC, id DESC LIMIT 60`,
        [user.id],
      )
    : [];
  const fronts = await q<{ edition_date: string; titles: string[] }>(
    `SELECT f.edition_date, array(SELECT p.title FROM unnest(f.seqs) WITH ORDINALITY s(seq, o) JOIN posts p ON p.seq = s.seq ORDER BY o) AS titles
     FROM (SELECT DISTINCT ON (edition_date) * FROM front_pages ORDER BY edition_date DESC, id DESC) f
     ORDER BY f.edition_date DESC LIMIT 30`,
  );
  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">지난 조간</h1>
      </div>
      {mine.length > 0 && (
        <>
          <section className="section" style={{ paddingTop: 0 }}>
            <div className="section-head"><h2 className="section-title">내 조간</h2></div>
            {mine.map((e) => (
              <Link key={e.id} href={`/e/${e.id}`} className="cell">
                <span className="body">
                  <span className="main">{kstDateLabel(e.edition_date)}</span>
                  <span className="under">{PRESET_KO[e.preset] ?? ""}</span>
                </span>
                <Chevron size={18} className="chev" />
              </Link>
            ))}
          </section>
          <div className="band" style={{ marginTop: 20 }} />
        </>
      )}
      <section className="section" style={mine.length ? undefined : { paddingTop: 0 }}>
        <div className="section-head"><h2 className="section-title">날짜별 1면</h2></div>
        {fronts.length === 0 && <p className="muted">아직 없어요.</p>}
        {fronts.map((f) => (
          <Link key={f.edition_date} href={`/front/${f.edition_date}`} className="cell" style={{ alignItems: "flex-start" }}>
            <span className="body">
              <span className="over">{kstDateLabel(f.edition_date)}</span>
              {f.titles.map((t, i) => <span key={i} className={i === 0 ? "main" : "under"}>{t}</span>)}
            </span>
            <Chevron size={18} className="chev" />
          </Link>
        ))}
      </section>
      <div style={{ height: 32 }} />
    </div>
  );
}
