import "server-only";
import { q } from "./db";
import type { Draft } from "@/components/DraftCard";

export async function pendingDrafts(limit = 100): Promise<Draft[]> {
  return q<Draft>(
    `SELECT d.id, d.kind::text AS kind, d.status, d.created_at, d.payload, d.verify_report,
            EXISTS (SELECT 1 FROM jobs j WHERE j.type IN ('publish_draft','reject_draft') AND j.status IN ('queued','running')
                    AND (j.payload->>'draft_id')::bigint = d.id) AS queued
     FROM drafts d WHERE d.status = 'pending' ORDER BY d.id LIMIT $1`,
    [limit],
  );
}

export function budgetUsd(): number {
  if (process.env.ONULPAN_BUDGET_USD) return Number(process.env.ONULPAN_BUDGET_USD);
  return process.env.ONULPAN_MODE === "launch" ? 400 : 30;
}
