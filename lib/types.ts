export type Candle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type Quote = {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  asOf: string;
  candles: Candle[];
  error?: string;
};

export type NaaimReading = {
  date: string;
  exposure: number;
  mostBearish: number;
  quartile1: number;
  median: number;
  quartile3: number;
  mostBullish: number;
  deviation: number;
};

export type NaaimRow = {
  date: string;
  exposure: number;
  change: number | null;
};

export type NaaimView = {
  latest: NaaimRow | null;
  rows: NaaimRow[];
  visibleCount: number;
  archivedCount: number;
  updatedAt: string | null;
};

export type AaiiWeek = {
  weekEnding: string;
  bullish: number;
  neutral: number;
  bearish: number;
};

export type AaiiHigh = {
  value: number;
  weekEnding: string;
};

export type AaiiChart = {
  recent: AaiiWeek[];
  averages: { bullish: number; neutral: number; bearish: number };
  highs: { bullish: AaiiHigh; neutral: AaiiHigh; bearish: AaiiHigh };
};

export type AaiiReading = {
  date: string;
  bullish: number;
  neutral: number;
  bearish: number;
};

export type AaiiStatusState = "current" | "waiting" | "retrying" | "error" | "empty";

export type AaiiView = {
  chart: AaiiChart | null;
  chartSource: "aaii.com" | "archive" | null;
  archivedCount: number;
  updatedAt: string | null;
  status: {
    state: AaiiStatusState;
    message: string;
    nextCheckAt: string | null;
    lastSuccessAt: string | null;
  };
};

export type DashboardPayload = {
  naaim: NaaimView;
  aaii: AaiiView;
};
