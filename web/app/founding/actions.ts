"use server";
import { randomBytes } from "node:crypto";
import { q } from "@/lib/db";
import { FOUNDING } from "@/lib/payments";
import { requireUser } from "@/lib/session";

export async function createOrder(): Promise<{ orderId: string; amount: number; orderName: string; customerKey: string; email: string }> {
  const user = await requireUser("/founding");
  const orderId = `OP${Date.now()}${randomBytes(4).toString("hex")}`;
  await q(
    "INSERT INTO payments (user_id, provider, order_id, product, amount) VALUES ($1, 'tosspayments', $2, $3, $4)",
    [user.id, orderId, FOUNDING.product, FOUNDING.amount],
  );
  await q("INSERT INTO events (user_id, name, props) VALUES ($1, 'checkout_start', $2)", [user.id, JSON.stringify({ orderId })]);
  return { orderId, amount: FOUNDING.amount, orderName: FOUNDING.name, customerKey: user.id, email: user.email };
}
