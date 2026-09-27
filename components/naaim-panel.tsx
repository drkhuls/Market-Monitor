import { formatSigned } from "@/lib/format";
import { formatLongDate, formatShortDate } from "@/lib/time";
import type { NaaimView } from "@/lib/types";

function exposureTone(exposure: number): string {
  if (exposure >= 100) return "text-up";
  if (exposure < 30) return "text-down";
  if (exposure < 60) return "text-amber-800";
  return "text-ink";
}

export function NaaimPanel({ naaim }: { naaim: NaaimView }) {
  const older = Math.max(0, naaim.archivedCount - naaim.visibleCount);
  return (
    <section className="rounded-2xl border border-line bg-white p-4 shadow-[0_1px_2px_rgba(20,32,43,0.04),0_12px_32px_rgba(20,32,43,0.04)] sm:p-5">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
        <div className="lg:w-64 lg:shrink-0">
          <h2 className="text-xs font-semibold tracking-[0.14em] text-muted uppercase">NAAIM Exposure Index</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink/80">
            Average U.S. equity exposure reported by active managers. 0 is flat, 100 is fully long.
          </p>
          {naaim.latest ? (
            <>
              <p className={`mt-4 font-mono text-5xl font-semibold tracking-tight tabular-nums ${exposureTone(naaim.latest.exposure)}`}>
                {naaim.latest.exposure.toFixed(2)}
              </p>
              <p className="mt-1 text-sm text-ink">Week of {formatLongDate(naaim.latest.date)}</p>
              {naaim.latest.change != null ? (
                <p className="mt-1 font-mono text-sm text-muted tabular-nums">
                  {formatSigned(naaim.latest.change)} from the prior week
                </p>
              ) : null}
            </>
          ) : (
            <p className="mt-4 text-sm text-rose-700">No NAAIM readings have been saved yet.</p>
          )}
          <p className="mt-4 text-xs leading-relaxed text-muted">
            NAAIM posts this public series three months after the survey. New weeks are added when they show up.
          </p>
        </div>

        <div className="min-w-0 flex-1">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <h3 className="text-sm font-semibold text-ink">Last 12 months</h3>
            <p className="text-xs text-muted">{naaim.visibleCount} weeks</p>
          </div>
          <div className="max-h-[32rem] overflow-auto rounded-xl border border-line">
            <table className="w-full border-collapse text-[13px] text-ink">
              <caption className="sr-only">NAAIM exposure readings for the last 12 months</caption>
              <thead className="sticky top-0 bg-[#f6f8fb] text-left text-[11px] font-semibold tracking-wide text-muted uppercase">
                <tr>
                  <th className="px-3 py-2 font-semibold">Week</th>
                  <th className="px-3 py-2 text-right font-semibold">Exposure</th>
                  <th className="px-3 py-2 text-right font-semibold">Change</th>
                </tr>
              </thead>
              <tbody>
                {naaim.rows.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-3 py-6 text-sm text-muted">
                      Nothing in the last year is on file yet.
                    </td>
                  </tr>
                ) : (
                  naaim.rows.map((row, index) => (
                    <tr key={row.date} className={index % 2 === 0 ? "bg-white" : "bg-[#f8fafc]"}>
                      <td className="px-3 py-1.5 font-medium tabular-nums">{formatShortDate(row.date)}</td>
                      <td className={`px-3 py-1.5 text-right font-mono font-medium tabular-nums ${exposureTone(row.exposure)}`}>
                        {row.exposure.toFixed(2)}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted">
                        {row.change == null ? "—" : formatSigned(row.change)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            Older weeks leave this table and stay in <span className="font-mono">data/naaim-history.json</span>
            {older > 0 ? ` (${older} already archived)` : ""}.
          </p>
        </div>
      </div>
    </section>
  );
}
