import { NextResponse } from "next/server";
import { endSession, siteUrl } from "@/lib/session";

export async function POST() {
  await endSession();
  return NextResponse.redirect(`${siteUrl()}/`, 303);
}
