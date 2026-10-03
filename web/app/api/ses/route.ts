import { NextResponse } from "next/server";
import { q } from "@/lib/db";
import { isAwsUrl, type SnsMessage, verifySns } from "@/lib/sns";

// SES 반송(Bounce)·수신 거부(Complaint) 웹훅. 영구 반송과 스팸 신고 주소에는 더 보내지 않는다.
export async function POST(req: Request) {
  const msg = (await req.json().catch(() => null)) as SnsMessage | null;
  if (!msg || !(await verifySns(msg))) return new NextResponse("bad signature", { status: 403 });
  if (msg.Type === "SubscriptionConfirmation" && msg.SubscribeURL && isAwsUrl(msg.SubscribeURL, "sns")) {
    await fetch(msg.SubscribeURL);
    return new NextResponse("subscribed");
  }
  if (msg.Type !== "Notification") return new NextResponse("ignored");
  const n = JSON.parse(msg.Message) as {
    notificationType?: string; eventType?: string;
    bounce?: { bounceType: string; bouncedRecipients: { emailAddress: string }[] };
    complaint?: { complainedRecipients: { emailAddress: string }[] };
  };
  const type = n.notificationType ?? n.eventType;
  let recipients: string[] = [];
  let reason = "";
  if (type === "Bounce" && n.bounce?.bounceType === "Permanent") {
    recipients = n.bounce.bouncedRecipients.map((r) => r.emailAddress);
    reason = "bounce";
  } else if (type === "Complaint" && n.complaint) {
    recipients = n.complaint.complainedRecipients.map((r) => r.emailAddress);
    reason = "complaint";
  }
  for (const email of recipients) {
    const e = email.trim().toLowerCase();
    await q("INSERT INTO email_suppressions (email, reason) VALUES ($1, $2) ON CONFLICT (email) DO NOTHING", [e, reason]);
    await q(
      "UPDATE user_prefs SET email_enabled = false WHERE user_id = (SELECT id FROM users WHERE email = $1)",
      [e],
    );
  }
  return new NextResponse("ok");
}
