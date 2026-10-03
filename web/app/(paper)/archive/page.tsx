import Link from "next/link";
import { q } from "@/lib/db";
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
    <>
      <h1>지난 조간</h1>
      {mine.length > 0 && (
        <section>
          <h2 className="section-head">내가 받은 조간</h2>
          <ul>
            {mine.map((e) => (
              <li key={e.id}><Link href={`/e/${e.id}`}>{kstDateLabel(e.edition_date)}</Link></li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <h2 className="section-head">날짜별 1면</h2>
        {fronts.length === 0 && <p className="muted">아직 없습니다.</p>}
        {fronts.map((f) => (
          <div key={f.edition_date} className="post">
            <p className="kicker"><Link href={`/front/${f.edition_date}`}>{kstDateLabel(f.edition_date)}</Link></p>
            <ul>{f.titles.map((t, i) => <li key={i}>{t}</li>)}</ul>
          </div>
        ))}
      </section>
    </>
  );
}
