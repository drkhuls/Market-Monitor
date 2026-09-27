import type { Candle, Quote } from "@/lib/types";

const YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart";
const TTL_MS = 60_000;

const cache = new Map<string, { at: number; quote: Quote }>();

type YahooChart = {
  chart?: {
    result?: Array<{
      meta?: {
        regularMarketPrice?: number;
        previousClose?: number;
        chartPreviousClose?: number;
        regularMarketTime?: number;
      };
      timestamp?: number[];
      indicators?: {
        quote?: Array<{
          open?: Array<number | null>;
          high?: Array<number | null>;
          low?: Array<number | null>;
          close?: Array<number | null>;
        }>;
      };
    }>;
    error?: { description?: string };
  };
};

function dayKey(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toISOString().slice(0, 10);
}

export async function fetchQuote(symbol: string): Promise<Quote> {
  const url = `${YAHOO}/${encodeURIComponent(symbol)}?interval=1d&range=2y&includePrePost=false&events=div%7Csplit`;
  const response = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
      Accept: "application/json",
    },
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) {
    throw new Error(`${symbol} quote request failed (${response.status})`);
  }
  const body = (await response.json()) as YahooChart;
  const result = body.chart?.result?.[0];
  const timestamps = result?.timestamp;
  const quote = result?.indicators?.quote?.[0];
  if (!result || !timestamps || !quote) {
    throw new Error(body.chart?.error?.description || `No price data for ${symbol}`);
  }

  const candles: Candle[] = [];
  for (let i = 0; i < timestamps.length; i += 1) {
    const open = quote.open?.[i];
    const high = quote.high?.[i];
    const low = quote.low?.[i];
    const close = quote.close?.[i];
    if (open == null || high == null || low == null || close == null) continue;
    const time = dayKey(timestamps[i]);
    const previous = candles[candles.length - 1];
    if (previous?.time === time) {
      candles[candles.length - 1] = { time, open: previous.open, high: Math.max(previous.high, high), low: Math.min(previous.low, low), close };
      continue;
    }
    candles.push({ time, open, high, low, close });
  }
  if (candles.length < 2) throw new Error(`Not enough candles for ${symbol}`);

  const price = result.meta?.regularMarketPrice ?? candles[candles.length - 1].close;
  const previousClose =
    result.meta?.previousClose ??
    result.meta?.chartPreviousClose ??
    candles[candles.length - 2].close;
  const change = price - previousClose;
  const changePercent = previousClose ? (change / previousClose) * 100 : 0;
  const asOf = result.meta?.regularMarketTime
    ? new Date(result.meta.regularMarketTime * 1000).toISOString()
    : new Date().toISOString();

  return { symbol, price, change, changePercent, asOf, candles };
}

export async function getQuotes(symbols: string[]): Promise<Quote[]> {
  return Promise.all(
    symbols.map(async (symbol) => {
      const hit = cache.get(symbol);
      if (hit && Date.now() - hit.at < TTL_MS) return hit.quote;
      try {
        const quote = await fetchQuote(symbol);
        cache.set(symbol, { at: Date.now(), quote });
        return quote;
      } catch (error) {
        if (hit) return hit.quote;
        const message = error instanceof Error ? error.message : "Quote unavailable";
        return {
          symbol,
          price: 0,
          change: 0,
          changePercent: 0,
          asOf: new Date().toISOString(),
          candles: [],
          error: message,
        };
      }
    }),
  );
}

export function clearQuoteCache(): void {
  cache.clear();
}
