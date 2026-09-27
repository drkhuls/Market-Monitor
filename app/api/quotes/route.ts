import { NextResponse } from "next/server";

import { loadQuotes } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

export async function GET() {
  const quotes = await loadQuotes();
  return NextResponse.json({ quotes });
}
