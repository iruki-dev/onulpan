import "server-only";
import { createVerify } from "node:crypto";

// Amazon SNS 메시지 서명 검증 (SES 반송·수신 거부 알림). 인증서는 sns.*.amazonaws.com에서만 받는다.
export type SnsMessage = {
  Type: string; MessageId: string; TopicArn: string; Message: string; Timestamp: string; SignatureVersion: string;
  Signature: string; SigningCertURL: string; Subject?: string; SubscribeURL?: string; Token?: string;
};

const certCache = new Map<string, string>();

export function isAwsUrl(u: string, prefix: "sns"): boolean {
  try {
    const url = new URL(u);
    return url.protocol === "https:" && new RegExp(`^${prefix}\\.[a-z0-9-]+\\.amazonaws\\.com$`).test(url.hostname);
  } catch {
    return false;
  }
}

export function stringToSign(m: SnsMessage): string {
  const keys = m.Type === "Notification"
    ? ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
    : ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"];
  return keys
    .filter((k) => (m as Record<string, unknown>)[k] !== undefined)
    .map((k) => `${k}\n${(m as Record<string, unknown>)[k]}\n`)
    .join("");
}

export async function verifySns(m: SnsMessage): Promise<boolean> {
  if (!isAwsUrl(m.SigningCertURL, "sns")) return false;
  let pem = certCache.get(m.SigningCertURL);
  if (!pem) {
    const r = await fetch(m.SigningCertURL);
    if (!r.ok) return false;
    pem = await r.text();
    certCache.set(m.SigningCertURL, pem);
  }
  const algo = m.SignatureVersion === "2" ? "RSA-SHA256" : "RSA-SHA1";
  return createVerify(algo).update(stringToSign(m), "utf8").verify(pem, m.Signature, "base64");
}
