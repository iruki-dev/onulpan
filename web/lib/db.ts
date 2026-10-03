import "server-only";
import pg from "pg";

// 웹은 읽기 위주(app_reader). 워커가 쓰고, 웹이 읽는다.
pg.types.setTypeParser(20, (v) => Number(v)); // bigint(seq 등) → number. 2^53 미만에서 안전
pg.types.setTypeParser(1700, (v) => Number(v)); // numeric(비용) → number
(pg.types.setTypeParser as (oid: number, fn: (v: string) => unknown) => void)(1016, (v) => (v === "{}" ? [] : v.slice(1, -1).split(",").map(Number))); // bigint[] (1면 seqs)
pg.types.setTypeParser(1082, (v) => v); // date는 'YYYY-MM-DD' 문자열 그대로 (시간대 변환 방지)

const g = globalThis as unknown as { __onulpanPool?: pg.Pool };

export const pool =
  g.__onulpanPool ??
  new pg.Pool({
    connectionString:
      process.env.DATABASE_URL_WEB ?? process.env.DATABASE_URL ?? "postgresql://onulpan:onulpan@localhost:5432/onulpan",
    max: Number(process.env.PG_POOL_MAX ?? 10),
  });
if (process.env.NODE_ENV !== "production") g.__onulpanPool = pool;

export async function q<T = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<T[]> {
  const r = await pool.query(sql, params);
  return r.rows as T[];
}

export async function one<T = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<T | null> {
  const rows = await q<T>(sql, params);
  return rows[0] ?? null;
}

/** 워커에 작업을 넣는다 (재조립, 초안 게시 등). 웹은 편집기를 갖지 않는다. */
export async function enqueue(type: string, payload: Record<string, unknown>): Promise<void> {
  await q("INSERT INTO jobs (type, payload) VALUES ($1, $2)", [type, JSON.stringify(payload)]);
}
