import "server-only";
import { LICENSES } from "./labels";
import { one, q } from "./db";

/** 화면에 실을 수 있는 이미지 한 장과 그 표기. 크레딧은 이미지 바로 아래에 그대로 쓴다. */
export type Img = {
  id: number;
  src: string;
  width: number | null;
  height: number | null;
  alt: string;
  credit: string;
  license: string;
  licenseLabel: string;
  licenseUrl: string | null;
  linkRequired: boolean;
  originUrl: string;
  sourceName: string;
  tier: "free" | "press" | "own";
  modifiable: boolean;
  usageTerms: string | null;
  title: string | null;
  status: string;
};

type Row = {
  id: number; post_seq?: number; hotlink: boolean; file_url: string | null; width: number | null; height: number | null;
  alt: string; credit: string; license: string; license_url: string | null; origin_url: string; source_name: string;
  tier: Img["tier"]; modifiable: boolean; usage_terms: string | null; title: string | null; status: string;
};

const COLS = `i.id, i.hotlink, i.file_url, i.width, i.height, i.alt, i.credit, i.license, i.license_url, i.origin_url,
  s.name AS source_name, s.tier::text AS tier, i.modifiable, i.usage_terms, i.title, i.status`;

export function toImg(r: Row): Img {
  const lic = LICENSES[r.license];
  return {
    id: r.id, src: r.hotlink && r.file_url ? r.file_url : `/img/${r.id}`, width: r.width, height: r.height, alt: r.alt,
    credit: r.credit, license: r.license, licenseLabel: lic?.label ?? r.license, licenseUrl: r.license_url ?? lic?.url ?? null,
    linkRequired: Boolean(lic?.link), originUrl: r.origin_url, sourceName: r.source_name, tier: r.tier,
    modifiable: r.modifiable, usageTerms: r.usage_terms, title: r.title, status: r.status,
  };
}

/** 글별 대표 이미지. 승인되고(active) 내려지지 않은 것만. */
export async function leadImages(seqs: number[]): Promise<Map<number, Img>> {
  if (!seqs.length) return new Map();
  const rows = await q<Row>(
    `SELECT pi.post_seq, ${COLS} FROM post_images pi JOIN images i ON i.id = pi.image_id JOIN image_sources s ON s.key = i.source_key
     WHERE pi.post_seq = ANY($1::bigint[]) AND pi.status = 'active' AND pi.role = 'lead' AND i.status = 'active'
       AND (i.stored_path IS NOT NULL OR i.hotlink)`,
    [seqs],
  );
  return new Map(rows.map((r) => [r.post_seq!, toImg(r)]));
}

export async function imageById(id: number): Promise<Img | null> {
  const r = await one<Row>(`SELECT ${COLS} FROM images i JOIN image_sources s ON s.key = i.source_key WHERE i.id = $1`, [id]);
  return r ? toImg(r) : null;
}

export async function imageSources() {
  return q<{ key: string; name: string; tier: string; url: string | null; examples: string; conditions: string; auto: boolean }>(
    "SELECT key, name, tier::text AS tier, url, examples, conditions, auto FROM image_sources WHERE active ORDER BY ord",
  );
}
