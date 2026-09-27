import { NextRequest, NextResponse } from "next/server";

import { loadDashboard } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const refresh = request.nextUrl.searchParams.get("refresh") === "1";
  const dashboard = await loadDashboard({ refresh });
  return NextResponse.json(dashboard);
}
