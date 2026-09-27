"use client";

import { useEffect, useRef, useState } from "react";
import type { IChartApi, ISeriesApi, Time } from "lightweight-charts";

import { Button } from "@/components/ui/button";
import { formatPercent, formatPrice, formatSigned } from "@/lib/format";
import {
  DEFAULT_RANGE,
  logicalRangeWithRightBlank,
  RANGES,
  type RangeKey,
  visibleStartIndex,
} from "@/lib/range";
import { formatQuoteTime } from "@/lib/time";
import type { Quote } from "@/lib/types";

type CandleSeries = ISeriesApi<"Candlestick", Time>;

export function QuoteCard({
  quote,
  onRetry,
}: {
  quote: Quote;
  onRetry: () => void;
}) {
  const [range, setRange] = useState<RangeKey>(DEFAULT_RANGE);
  const frameRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<CandleSeries | null>(null);
  const rangeRef = useRef<RangeKey>(DEFAULT_RANGE);
  const candlesRef = useRef(quote.candles);
  const userMoved = useRef(false);
  const applying = useRef(false);

  useEffect(() => {
    candlesRef.current = quote.candles;
  }, [quote.candles]);

  useEffect(() => {
    rangeRef.current = range;
  }, [range]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || quote.candles.length === 0) return;
    let removed = false;
    let chart: IChartApi | null = null;

    void (async () => {
      const { CandlestickSeries, ColorType, createChart, CrosshairMode } = await import(
        "lightweight-charts"
      );
      if (removed || !frameRef.current) return;

      chart = createChart(frameRef.current, {
        autoSize: true,
        layout: {
          background: { type: ColorType.Solid, color: "#fbfcfd" },
          textColor: "#5c6b7a",
          fontFamily: "var(--font-plex), sans-serif",
          fontSize: 12,
        },
        grid: {
          vertLines: { color: "#e7edf3" },
          horzLines: { color: "#e7edf3" },
        },
        rightPriceScale: { borderColor: "#d5dee8", scaleMargins: { top: 0.08, bottom: 0.08 } },
        timeScale: { borderColor: "#d5dee8", rightOffset: 0, fixRightEdge: false },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: { color: "#8b99a8", labelBackgroundColor: "#14202b" },
          horzLine: { color: "#8b99a8", labelBackgroundColor: "#14202b" },
        },
        handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
        handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
      });
      if (removed) {
        chart.remove();
        return;
      }
      const series = chart.addSeries(CandlestickSeries, {
        upColor: "#0e8a3d",
        downColor: "#d01212",
        borderUpColor: "#0e8a3d",
        borderDownColor: "#d01212",
        wickUpColor: "#0e8a3d",
        wickDownColor: "#d01212",
        priceLineVisible: true,
        lastValueVisible: true,
      });
      const candles = candlesRef.current;
      series.setData(candles);
      chartRef.current = chart;
      seriesRef.current = series;

      const apply = () => {
        if (!chart) return;
        const current = candlesRef.current;
        if (current.length === 0) return;
        const start = visibleStartIndex(
          current.map((candle) => candle.time),
          rangeRef.current,
        );
        applying.current = true;
        chart.timeScale().setVisibleLogicalRange(logicalRangeWithRightBlank(start, current.length - 1));
        window.setTimeout(() => {
          applying.current = false;
        }, 200);
      };
      apply();
      window.setTimeout(apply, 50);
      chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
        if (!applying.current) userMoved.current = true;
      });
    })();

    return () => {
      removed = true;
      chart?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [quote.symbol, quote.candles.length]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series || quote.candles.length === 0) return;
    series.setData(quote.candles);
    if (userMoved.current) return;
    const times = quote.candles.map((candle) => candle.time);
    const start = visibleStartIndex(times, rangeRef.current);
    applying.current = true;
    chart.timeScale().setVisibleLogicalRange(logicalRangeWithRightBlank(start, quote.candles.length - 1));
    requestAnimationFrame(() => {
      applying.current = false;
    });
  }, [quote.candles]);

  function selectRange(next: RangeKey) {
    setRange(next);
    rangeRef.current = next;
    userMoved.current = false;
    const chart = chartRef.current;
    if (!chart || quote.candles.length === 0) return;
    const times = quote.candles.map((candle) => candle.time);
    const start = visibleStartIndex(times, next);
    applying.current = true;
    chart.timeScale().setVisibleLogicalRange(logicalRangeWithRightBlank(start, quote.candles.length - 1));
    requestAnimationFrame(() => {
      applying.current = false;
    });
  }

  const up = quote.change > 0;
  const down = quote.change < 0;

  return (
    <article className="flex min-w-0 flex-col rounded-2xl border border-line bg-white shadow-[0_1px_2px_rgba(20,32,43,0.04),0_12px_32px_rgba(20,32,43,0.04)]">
      <div className="flex flex-wrap items-start justify-between gap-3 px-4 pt-4 sm:px-5">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-ink">{quote.symbol}</h2>
          {quote.error ? (
            <p className="mt-2 max-w-sm text-sm text-rose-700">{quote.error}</p>
          ) : (
            <>
              <p className="mt-1 font-mono text-3xl font-semibold tracking-tight text-ink tabular-nums">
                {formatPrice(quote.price)}
              </p>
              <p
                className={`mt-1 font-mono text-sm font-medium tabular-nums ${up ? "text-up" : down ? "text-down" : "text-muted"}`}
              >
                {formatSigned(quote.change)} {formatPercent(quote.changePercent)}
                <span className="ml-2 font-sans font-normal text-muted">vs prior close</span>
              </p>
            </>
          )}
        </div>
        <div className="flex flex-col items-stretch gap-2 sm:items-end">
          <div className="flex flex-wrap gap-1" role="group" aria-label={`${quote.symbol} time range`}>
            {RANGES.map((item) => (
              <Button
                key={item}
                type="button"
                size="sm"
                variant={range === item ? "default" : "outline"}
                aria-pressed={range === item}
                onClick={() => selectRange(item)}
              >
                {item}
              </Button>
            ))}
          </div>
          {!quote.error && quote.asOf ? (
            <p className="text-right text-xs text-muted">As of {formatQuoteTime(quote.asOf)}</p>
          ) : null}
        </div>
      </div>
      {quote.error ? (
        <div className="px-4 py-8 sm:px-5">
          <Button type="button" variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </div>
      ) : (
        <div className="mt-3 h-[300px] px-2 pb-3 sm:h-[380px] sm:px-3">
          <div ref={frameRef} className="h-full w-full overflow-hidden rounded-xl" />
        </div>
      )}
    </article>
  );
}
