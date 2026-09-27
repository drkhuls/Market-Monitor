import { aaiiView, readAaiiArchive, readPollState } from "@/lib/aaii";
import { naaimView, readNaaimArchive } from "@/lib/naaim";
import { getQuotes } from "@/lib/quotes";
import { ensureFreshData, refreshAll } from "@/lib/scheduler";
import type { DashboardPayload, Quote } from "@/lib/types";

export const SYMBOLS = ["SPY", "QQQ"] as const;

export async function loadDashboard(options?: { refresh?: boolean }): Promise<DashboardPayload> {
  if (options?.refresh) {
    await refreshAll();
  } else {
    await ensureFreshData();
  }
  const [naaim, aaii, poll] = await Promise.all([readNaaimArchive(), readAaiiArchive(), readPollState()]);
  return {
    naaim: naaimView(naaim),
    aaii: aaiiView(aaii, poll),
  };
}

export async function loadQuotes(): Promise<Quote[]> {
  return getQuotes([...SYMBOLS]);
}
