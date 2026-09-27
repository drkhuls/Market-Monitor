import { formatPercent1 } from "@/lib/format";
import type { AaiiChart, AaiiView } from "@/lib/types";

function spread(chart: AaiiChart): number {
  const latest = chart.recent[0];
  return Math.round((latest.bullish - latest.bearish) * 10) / 10;
}

export function AaiiPanel({ aaii }: { aaii: AaiiView }) {
  const chart = aaii.chart;
  const latestSpread = chart ? spread(chart) : null;

  return (
    <section aria-label="AAII Investor Sentiment Survey">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-xs font-semibold tracking-[0.14em] text-muted uppercase">
            AAII Investor Sentiment Survey
          </h2>
          <p className="mt-1 text-sm text-ink/80">
            Individual investors, asked each week where the market is headed over the next six months.
          </p>
        </div>
        {latestSpread != null ? (
          <p className="font-mono text-sm text-ink tabular-nums">
            Bull–bear spread {latestSpread > 0 ? "+" : latestSpread < 0 ? "−" : ""}
            {Math.abs(latestSpread).toFixed(1)} pp
          </p>
        ) : null}
      </div>

      {chart ? (
        <div className="aaii">
          <div className="aaii-card">
            <h3>Recent weekly results</h3>
            <div className="aaii-chart">
              <div className="aaii-week aaii-week-head">
                <div className="aaii-date">Week Ending</div>
                <div className="aaii-votes">
                  <p>Sentiment Votes</p>
                  <span className="aaii-key">
                    <span className="aaii-legend aaii-bull" />
                    Bullish
                  </span>
                  <span className="aaii-key">
                    <span className="aaii-legend aaii-neut" />
                    Neutral
                  </span>
                  <span className="aaii-key">
                    <span className="aaii-legend aaii-bear" />
                    Bearish
                  </span>
                </div>
              </div>
              {chart.recent.map((week) => (
                <div className="aaii-week" key={week.weekEnding}>
                  <div className="aaii-datebars">
                    <div className="aaii-date">{week.weekEnding}</div>
                    <div className="aaii-bars">
                      <div className="aaii-bar aaii-bull" style={{ width: `${week.bullish}%` }}>
                        {formatPercent1(week.bullish)}
                      </div>
                      <div className="aaii-bar aaii-neut" style={{ width: `${week.neutral}%` }}>
                        {formatPercent1(week.neutral)}
                      </div>
                      <div className="aaii-bar aaii-bear" style={{ width: `${week.bearish}%` }}>
                        {formatPercent1(week.bearish)}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="aaii-card">
            <h3>Historical view</h3>
            <div className="aaii-chart">
              <div className="aaii-week">
                <div className="aaii-datebars">
                  <div className="aaii-date">Historical Averages</div>
                  <div className="aaii-bars">
                    <div className="aaii-bar aaii-bull" style={{ width: `${chart.averages.bullish}%` }}>
                      {formatPercent1(chart.averages.bullish)}
                    </div>
                    <div className="aaii-bar aaii-neut" style={{ width: `${chart.averages.neutral}%` }}>
                      {formatPercent1(chart.averages.neutral)}
                    </div>
                    <div className="aaii-bar aaii-bear" style={{ width: `${chart.averages.bearish}%` }}>
                      {formatPercent1(chart.averages.bearish)}
                    </div>
                  </div>
                </div>
              </div>
              <HighRow label="1-Year Bullish High" value={chart.highs.bullish.value} weekEnding={chart.highs.bullish.weekEnding} tone="bull" />
              <HighRow label="1-Year Neutral High" value={chart.highs.neutral.value} weekEnding={chart.highs.neutral.weekEnding} tone="neut" />
              <HighRow label="1-Year Bearish High" value={chart.highs.bearish.value} weekEnding={chart.highs.bearish.weekEnding} tone="bear" />
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-line bg-white p-5 text-sm text-rose-700">
          The AAII chart is not available yet. Leave the monitor running and it will try AAII.com again.
        </div>
      )}

      <p className="mt-2 text-xs leading-relaxed text-muted">{aaii.status.message}</p>
    </section>
  );
}

function HighRow({
  label,
  value,
  weekEnding,
  tone,
}: {
  label: string;
  value: number;
  weekEnding: string;
  tone: "bull" | "neut" | "bear";
}) {
  return (
    <div className="aaii-week">
      <div className="aaii-datebars">
        <div className="aaii-date">{label}</div>
        <div className="aaii-bars">
          <div className={`aaii-bar aaii-${tone}`} style={{ width: `${value}%` }}>
            {formatPercent1(value)}
          </div>
          <div className="aaii-ending">Week Ending {weekEnding}</div>
        </div>
      </div>
    </div>
  );
}
