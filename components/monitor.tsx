"use client";

import { useEffect, useState } from "react";

import { AaiiPanel } from "@/components/aaii-panel";
import { NaaimPanel } from "@/components/naaim-panel";
import { QuoteCard } from "@/components/quote-card";
import { Button } from "@/components/ui/button";
import { formatTodayLabel } from "@/lib/time";
import type { DashboardPayload, Quote } from "@/lib/types";

export function Monitor({
  quotes: initialQuotes,
  dashboard: initialDashboard,
}: {
  quotes: Quote[];
  dashboard: DashboardPayload;
}) {
  const [quotes, setQuotes] = useState(initialQuotes);
  const [dashboard, setDashboard] = useState(initialDashboard);
  const [refreshing, setRefreshing] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  async function refreshQuotes() {
    const response = await fetch("/api/quotes", { cache: "no-store" });
    if (!response.ok) throw new Error("Quotes could not be refreshed");
    const body = (await response.json()) as { quotes: Quote[] };
    setQuotes(body.quotes);
  }

  async function refreshDashboard(force: boolean) {
    const response = await fetch(force ? "/api/dashboard?refresh=1" : "/api/dashboard", { cache: "no-store" });
    if (!response.ok) throw new Error("Sentiment readings could not be refreshed");
    const body = (await response.json()) as DashboardPayload;
    setDashboard(body);
  }

  async function refreshAll(force = false) {
    setRefreshing(true);
    setBanner(null);
    try {
      await Promise.all([refreshQuotes(), refreshDashboard(force)]);
    } catch (error) {
      setBanner(error instanceof Error ? error.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    const quotesTimer = setInterval(() => {
      void refreshQuotes().catch(() => undefined);
    }, 60_000);
    const dashboardTimer = setInterval(() => {
      void refreshDashboard(false).catch(() => undefined);
    }, 5 * 60_000);
    return () => {
      clearInterval(quotesTimer);
      clearInterval(dashboardTimer);
    };
  }, []);

  return (
    <main className="mx-auto w-full max-w-[1180px] px-4 py-6 sm:px-6 sm:py-8">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-muted uppercase">Desk</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Market Monitor</h1>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink/75">
            SPY and QQQ, with the weekly NAAIM exposure reading and the AAII sentiment survey.
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          <p className="text-sm text-muted">{formatTodayLabel()}</p>
          <Button type="button" variant="outline" size="sm" disabled={refreshing} onClick={() => void refreshAll(true)}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </header>

      {banner ? (
        <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800" role="status">
          {banner}
        </p>
      ) : null}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {quotes.map((quote) => (
          <QuoteCard key={quote.symbol} quote={quote} onRetry={() => void refreshQuotes()} />
        ))}
      </div>

      <div className="mt-8">
        <AaiiPanel aaii={dashboard.aaii} />
      </div>

      <div className="mt-8">
        <NaaimPanel naaim={dashboard.naaim} />
      </div>

      <footer className="mt-8 border-t border-line pt-4 text-xs leading-relaxed text-muted">
        Prices from Yahoo Finance. NAAIM Exposure Index from the public NAAIM series. AAII Sentiment Survey from AAII.com,
        checked Thursday at 10:00 AM ET and every two hours after that until the new reading is up.
      </footer>
    </main>
  );
}
