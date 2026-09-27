import { addCalendarDays, todayIsoET } from "@/lib/time";
import { readJson, writeJson } from "@/lib/store";
import type { NaaimReading, NaaimRow, NaaimView } from "@/lib/types";

const FILE = "naaim-history.json";
const TABLE_URL = "https://index.naaim.org/embeddable/table";

export type NaaimArchive = {
  notes: string;
  source: string;
  updatedAt: string | null;
  readings: NaaimReading[];
};

const EMPTY: NaaimArchive = {
  notes:
    "Permanent archive of NAAIM Exposure Index readings collected from the public NAAIM table. The monitor shows only the last 12 months. Do not delete rows when they age off the table.",
  source: TABLE_URL,
  updatedAt: null,
  readings: [],
};

const ROW_PATTERN =
  /<tr>\s*<td>(\d{2}\/\d{2}\/\d{4})<\/td>\s*<td[^>]*>([^<]*)<\/td>\s*<td[^>]*>([^<]*)<\/td>\s*<td[^>]*>([^<]*)<\/td>\s*<td[^>]*>([^<]*)<\/td>\s*<td[^>]*>([^<]*)<\/td>\s*<td[^>]*>([^<]*)<\/td>\s*<td[^>]*>([^<]*)<\/td>\s*<\/tr>/g;

function toIso(usDate: string): string {
  const [month, day, year] = usDate.split("/");
  return `${year}-${month}-${day}`;
}

function num(value: string): number {
  const parsed = Number(value.replace(/,/g, "").trim());
  if (!Number.isFinite(parsed)) throw new Error(`Unexpected NAAIM value "${value}"`);
  return parsed;
}

export function parseNaaimTable(html: string): NaaimReading[] {
  const readings: NaaimReading[] = [];
  for (const match of html.matchAll(ROW_PATTERN)) {
    readings.push({
      date: toIso(match[1]),
      exposure: num(match[2]),
      mostBearish: num(match[3]),
      quartile1: num(match[4]),
      median: num(match[5]),
      quartile3: num(match[6]),
      mostBullish: num(match[7]),
      deviation: num(match[8]),
    });
  }
  readings.sort((a, b) => a.date.localeCompare(b.date));
  return readings;
}

function merge(existing: NaaimReading[], incoming: NaaimReading[]): NaaimReading[] {
  const byDate = new Map<string, NaaimReading>();
  for (const reading of existing) byDate.set(reading.date, reading);
  for (const reading of incoming) byDate.set(reading.date, reading);
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export async function readNaaimArchive(): Promise<NaaimArchive> {
  return readJson<NaaimArchive>(FILE, EMPTY);
}

export async function refreshNaaim(): Promise<NaaimArchive> {
  const response = await fetch(TABLE_URL, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
      Accept: "text/html",
    },
    cache: "no-store",
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) throw new Error(`NAAIM table request failed (${response.status})`);
  const html = await response.text();
  const incoming = parseNaaimTable(html);
  if (incoming.length < 20) {
    throw new Error("NAAIM table did not include a usable history");
  }
  const existing = await readNaaimArchive();
  const archive: NaaimArchive = {
    ...EMPTY,
    ...existing,
    notes: EMPTY.notes,
    source: TABLE_URL,
    updatedAt: new Date().toISOString(),
    readings: merge(existing.readings ?? [], incoming),
  };
  await writeJson(FILE, archive);
  console.log(`[naaim] stored ${archive.readings.length} readings, latest ${archive.readings.at(-1)?.date}`);
  return archive;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

export function naaimView(archive: NaaimArchive, now = new Date()): NaaimView {
  const readings = [...(archive.readings ?? [])].sort((a, b) => a.date.localeCompare(b.date));
  const changeByDate = new Map<string, number | null>();
  readings.forEach((reading, index) => {
    const previous = readings[index - 1];
    changeByDate.set(reading.date, previous ? round2(reading.exposure - previous.exposure) : null);
  });
  const cutoff = addCalendarDays(todayIsoET(now), -365);
  const rows: NaaimRow[] = readings
    .filter((reading) => reading.date >= cutoff)
    .map((reading) => ({
      date: reading.date,
      exposure: reading.exposure,
      change: changeByDate.get(reading.date) ?? null,
    }))
    .sort((a, b) => b.date.localeCompare(a.date));

  return {
    latest: rows[0] ?? null,
    rows,
    visibleCount: rows.length,
    archivedCount: readings.length,
    updatedAt: archive.updatedAt,
  };
}
