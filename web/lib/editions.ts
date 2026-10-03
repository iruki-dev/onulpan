import "server-only";
import { enqueue, one, q } from "./db";

export type Slot = { slot: string; seq?: number; code?: string; section?: string; niche?: boolean };
export type Edition = {
  id: number;
  user_id: string;
  edition_date: string;
  as_of_seq: number;
  preset: string;
  slots: Slot[];
  editor_version: string;
  created_at: Date;
};

export async function latestEdition(userId: string, date: string): Promise<Edition | null> {
  return one<Edition>(
    "SELECT * FROM editions WHERE user_id = $1 AND edition_date = $2 ORDER BY id DESC LIMIT 1",
    [userId, date],
  );
}

export async function editionById(id: number, userId: string): Promise<Edition | null> {
  return one<Edition>("SELECT * FROM editions WHERE id = $1 AND user_id = $2", [id, userId]);
}

/** 조간이 아직 없으면 워커에 조립을 맡긴다. 같은 요청이 이미 대기 중이면 다시 넣지 않는다. */
export async function requestAssembly(userId: string): Promise<void> {
  const pending = await one(
    "SELECT 1 FROM jobs WHERE type = 'assemble_edition' AND status IN ('queued','running') AND payload->>'user_id' = $1",
    [userId],
  );
  if (!pending) await enqueue("assemble_edition", { user_id: userId });
}

/** 마지막으로 연 조간의 as_of_seq. 뒤로 가지 않는다. */
export async function advanceCursor(userId: string, asOfSeq: number): Promise<void> {
  await q(
    `INSERT INTO reading_cursors (user_id, last_seq, updated_at) VALUES ($1, $2, now())
     ON CONFLICT (user_id) DO UPDATE SET last_seq = GREATEST(reading_cursors.last_seq, EXCLUDED.last_seq),
       updated_at = CASE WHEN EXCLUDED.last_seq > reading_cursors.last_seq THEN now() ELSE reading_cursors.updated_at END`,
    [userId, asOfSeq],
  );
}

export type Front = { id: number; edition_date: string; seqs: number[]; fallback: boolean; issue_seq: number | null };

export async function latestFront(date?: string): Promise<Front | null> {
  return date
    ? one<Front>("SELECT * FROM front_pages WHERE edition_date <= $1 ORDER BY edition_date DESC, id DESC LIMIT 1", [date])
    : one<Front>("SELECT * FROM front_pages ORDER BY edition_date DESC, id DESC LIMIT 1");
}
