import { aaiiCheckIsDue, readAaiiArchive, readPollState, refreshAaii } from "@/lib/aaii";
import { readNaaimArchive, refreshNaaim } from "@/lib/naaim";

let inflight: Promise<void> | null = null;

export function refreshAll(): Promise<void> {
  if (inflight) return inflight;
  inflight = (async () => {
    const [naaim, aaii] = await Promise.allSettled([refreshNaaim(), refreshAaii()]);
    if (naaim.status === "rejected") {
      console.error("[naaim]", naaim.reason instanceof Error ? naaim.reason.message : naaim.reason);
    }
    if (aaii.status === "rejected") {
      console.error("[aaii]", aaii.reason instanceof Error ? aaii.reason.message : aaii.reason);
    }
  })().finally(() => {
    inflight = null;
  });
  return inflight;
}

async function archivesReady(): Promise<boolean> {
  const [naaim, aaii] = await Promise.all([readNaaimArchive(), readAaiiArchive()]);
  return (naaim.readings?.length ?? 0) > 0 && (aaii.readings?.length ?? 0) > 0 && Boolean(aaii.chart);
}

async function tick(): Promise<void> {
  const [ready, poll] = await Promise.all([archivesReady(), readPollState()]);
  if (!ready || aaiiCheckIsDue(poll)) {
    await refreshAll();
  }
}

export function startScheduler(): void {
  const globalState = globalThis as { __marketMonitorScheduler?: boolean };
  if (globalState.__marketMonitorScheduler) return;
  globalState.__marketMonitorScheduler = true;
  void tick();
  setInterval(() => {
    void tick();
  }, 60_000);
}

export async function ensureFreshData(): Promise<void> {
  startScheduler();
  const [ready, poll] = await Promise.all([archivesReady(), readPollState()]);
  if (!ready || aaiiCheckIsDue(poll)) {
    await refreshAll();
  }
}
