export const RANGES = ["1M", "3M", "6M", "YTD", "1Y"] as const;
export type RangeKey = (typeof RANGES)[number];
export const DEFAULT_RANGE: RangeKey = "3M";

/** Share of the chart width left empty to the right of the latest candle. */
export const RIGHT_BLANK_RATIO = 0.23;

export function rangeStartDate(lastIso: string, key: RangeKey): string {
  const [year, month, day] = lastIso.split("-").map(Number);
  if (key === "YTD") return `${year}-01-01`;
  const date = new Date(Date.UTC(year, month - 1, day));
  if (key === "1M") date.setUTCMonth(date.getUTCMonth() - 1);
  if (key === "3M") date.setUTCMonth(date.getUTCMonth() - 3);
  if (key === "6M") date.setUTCMonth(date.getUTCMonth() - 6);
  if (key === "1Y") date.setUTCFullYear(date.getUTCFullYear() - 1);
  return date.toISOString().slice(0, 10);
}

export function visibleStartIndex(times: string[], key: RangeKey): number {
  if (times.length === 0) return 0;
  const start = rangeStartDate(times[times.length - 1], key);
  const index = times.findIndex((time) => time >= start);
  return index < 0 ? 0 : index;
}

/**
 * Logical range whose empty region, measured from the right edge of the last
 * candle to the right edge of the plot, is 23% of the visible width.
 */
export function logicalRangeWithRightBlank(startIndex: number, lastIndex: number) {
  const candleRight = lastIndex + 0.5;
  const to = (candleRight - RIGHT_BLANK_RATIO * startIndex) / (1 - RIGHT_BLANK_RATIO);
  return { from: startIndex, to };
}
