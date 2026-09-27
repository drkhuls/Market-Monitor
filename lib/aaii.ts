import XLSX from "xlsx";

import { readJson, writeJson } from "@/lib/store";
import {
  addCalendarDays,
  expectedAaiiReportedDate,
  formatEtInstant,
  formatLongDate,
  thursdayAtTenEt,
} from "@/lib/time";
import type { AaiiChart, AaiiReading, AaiiStatusState, AaiiView } from "@/lib/types";

const FILE = "aaii-history.json";
const POLL_FILE = "poll-state.json";
const SURVEY_URL = "https://www.aaii.com/sentimentsurvey";
const XLS_URL = "https://www.aaii.com/files/surveys/sentiment.xls";
const TWO_HOURS_MS = 2 * 60 * 60 * 1000;

const BROWSER_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
  Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "Accept-Language": "en-US,en;q=0.9",
};

export type AaiiArchive = {
  notes: string;
  source: string;
  updatedAt: string | null;
  readings: AaiiReading[];
  chart: AaiiChart | null;
  chartSource: "aaii.com" | "archive" | null;
};

export type PollState = {
  lastAttemptAt: string | null;
  lastSuccessAt: string | null;
  latestReportedDate: string | null;
  nextCheckAt: string | null;
  state: AaiiStatusState;
  message: string;
  lastError: string | null;
};

const EMPTY_ARCHIVE: AaiiArchive = {
  notes:
    "Permanent archive of the AAII Investor Sentiment Survey. Readings come from the official sentiment.xls file on AAII.com. The chart block is the weekly bar chart copied from the survey page. Do not delete old weeks.",
  source: XLS_URL,
  updatedAt: null,
  readings: [],
  chart: null,
  chartSource: null,
};

const EMPTY_POLL: PollState = {
  lastAttemptAt: null,
  lastSuccessAt: null,
  latestReportedDate: null,
  nextCheckAt: null,
  state: "empty",
  message: "The AAII survey has not been collected yet.",
  lastError: null,
};

function cookieHeader(response: Response): string {
  const headers = response.headers as Headers & { getSetCookie?: () => string[] };
  const parts = headers.getSetCookie?.() ?? [];
  return parts
    .map((cookie) => cookie.split(";")[0]?.trim())
    .filter(Boolean)
    .join("; ");
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

function percentIn(chunk: string, kind: "bullish" | "neutral" | "bearish"): number | null {
  const match = chunk.match(new RegExp(`class="bar ${kind}"[^>]*>([\\d.]+)%`));
  return match ? Number(match[1]) : null;
}

export function parseAaiiChart(html: string): AaiiChart | null {
  const start = html.indexOf("Recent weekly results");
  if (start < 0) return null;
  const end = html.indexOf("More Historical", start);
  const section = html.slice(start, end === -1 ? start + 30_000 : end);
  const chunks = section.split(/<div class="date[^"]*">/).slice(1);

  const recent: AaiiChart["recent"] = [];
  let averages: AaiiChart["averages"] | null = null;
  const highs: Partial<AaiiChart["highs"]> = {};

  for (const chunk of chunks) {
    const label = chunk.slice(0, chunk.indexOf("</div>")).replace(/<[^>]+>/g, "").trim();
    if (!label || label === "Week Ending") continue;
    const ending = chunk.match(/class="ending">([^<]+)/)?.[1]?.trim();
    const bullish = percentIn(chunk, "bullish");
    const neutral = percentIn(chunk, "neutral");
    const bearish = percentIn(chunk, "bearish");

    if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(label) && bullish != null && neutral != null && bearish != null) {
      recent.push({ weekEnding: label, bullish, neutral, bearish });
      continue;
    }
    if (label === "Historical Averages" && bullish != null && neutral != null && bearish != null) {
      averages = { bullish, neutral, bearish };
      continue;
    }
    const weekEnding = ending?.replace(/^Week Ending\s+/i, "") ?? "";
    if (label === "1-Year Bullish High" && bullish != null && weekEnding) {
      highs.bullish = { value: bullish, weekEnding };
    } else if (label === "1-Year Neutral High" && neutral != null && weekEnding) {
      highs.neutral = { value: neutral, weekEnding };
    } else if (label === "1-Year Bearish High" && bearish != null && weekEnding) {
      highs.bearish = { value: bearish, weekEnding };
    }
  }

  if (!averages || recent.length < 4 || !highs.bullish || !highs.neutral || !highs.bearish) {
    return null;
  }
  return { recent, averages, highs: highs as AaiiChart["highs"] };
}

function weekEndingLabel(reportedIso: string): string {
  const previous = addCalendarDays(reportedIso, -1);
  const [year, month, day] = previous.split("-").map(Number);
  return `${month}/${day}/${year}`;
}

export function deriveAaiiChart(readings: AaiiReading[]): AaiiChart | null {
  if (readings.length === 0) return null;
  const ordered = [...readings].sort((a, b) => a.date.localeCompare(b.date));
  const recent = ordered
    .slice(-4)
    .reverse()
    .map((reading) => ({
      weekEnding: weekEndingLabel(reading.date),
      bullish: round1(reading.bullish),
      neutral: round1(reading.neutral),
      bearish: round1(reading.bearish),
    }));
  const count = ordered.length;
  const averages = {
    bullish: round1(ordered.reduce((sum, reading) => sum + reading.bullish, 0) / count),
    neutral: round1(ordered.reduce((sum, reading) => sum + reading.neutral, 0) / count),
    bearish: round1(ordered.reduce((sum, reading) => sum + reading.bearish, 0) / count),
  };
  const latest = ordered[ordered.length - 1].date;
  const cutoff = addCalendarDays(latest, -365);
  const year = ordered.filter((reading) => reading.date >= cutoff);
  const pool = year.length > 0 ? year : ordered;
  const bullish = pool.reduce((best, reading) => (reading.bullish > best.bullish ? reading : best));
  const neutral = pool.reduce((best, reading) => (reading.neutral > best.neutral ? reading : best));
  const bearish = pool.reduce((best, reading) => (reading.bearish > best.bearish ? reading : best));
  return {
    recent,
    averages,
    highs: {
      bullish: { value: round1(bullish.bullish), weekEnding: weekEndingLabel(bullish.date) },
      neutral: { value: round1(neutral.neutral), weekEnding: weekEndingLabel(neutral.date) },
      bearish: { value: round1(bearish.bearish), weekEnding: weekEndingLabel(bearish.date) },
    },
  };
}

export function parseSentimentWorkbook(buffer: Buffer): AaiiReading[] {
  const workbook = XLSX.read(buffer, { type: "buffer", cellDates: false });
  const sheet = workbook.Sheets.SENTIMENT;
  if (!sheet) throw new Error("AAII workbook is missing the SENTIMENT sheet");
  const rows = XLSX.utils.sheet_to_json<Array<string | number | null>>(sheet, {
    header: 1,
    raw: true,
  });
  const epoch = Date.UTC(1899, 11, 30);
  const readings: AaiiReading[] = [];
  for (const row of rows) {
    const serial = row?.[0];
    const bullish = row?.[1];
    const neutral = row?.[2];
    const bearish = row?.[3];
    if (typeof serial !== "number" || serial < 30_000) continue;
    if (typeof bullish !== "number" || typeof neutral !== "number" || typeof bearish !== "number") continue;
    if (bullish <= 0 && neutral <= 0 && bearish <= 0) continue;
    readings.push({
      date: new Date(epoch + serial * 86_400_000).toISOString().slice(0, 10),
      bullish: round4(bullish * 100),
      neutral: round4(neutral * 100),
      bearish: round4(bearish * 100),
    });
  }
  readings.sort((a, b) => a.date.localeCompare(b.date));
  return readings;
}

function mergeReadings(existing: AaiiReading[], incoming: AaiiReading[]): AaiiReading[] {
  const byDate = new Map<string, AaiiReading>();
  for (const reading of existing) byDate.set(reading.date, reading);
  for (const reading of incoming) byDate.set(reading.date, reading);
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export async function readAaiiArchive(): Promise<AaiiArchive> {
  return readJson<AaiiArchive>(FILE, EMPTY_ARCHIVE);
}

export async function readPollState(): Promise<PollState> {
  return readJson<PollState>(POLL_FILE, EMPTY_POLL);
}

function isCurrent(latest: string | null, now: Date): boolean {
  if (!latest) return false;
  return latest >= expectedAaiiReportedDate(now);
}

function nextCheckDate(now: Date, latest: string | null): Date {
  const expected = expectedAaiiReportedDate(now);
  if (latest && latest >= expected) {
    return thursdayAtTenEt(addCalendarDays(expected, 7));
  }
  const release = thursdayAtTenEt(expected);
  if (now.getTime() < release.getTime()) return release;
  return new Date(now.getTime() + TWO_HOURS_MS);
}

function describe(now: Date, latest: string | null, next: Date, error: string | null): Pick<PollState, "state" | "message"> {
  if (!latest && error) {
    return {
      state: "error",
      message: `Couldn't reach AAII.com. ${error} Trying again ${formatEtInstant(next)}.`,
    };
  }
  if (!latest) {
    return { state: "empty", message: "The AAII survey has not been collected yet." };
  }
  if (isCurrent(latest, now)) {
    return {
      state: "current",
      message: `Survey is current through the ${formatLongDate(latest)} release. Next check ${formatEtInstant(next)}.`,
    };
  }
  if (error) {
    return {
      state: "error",
      message: `This week's survey is not on AAII.com yet. ${error} Checking again ${formatEtInstant(next)}.`,
    };
  }
  return {
    state: "retrying",
    message: `This week's survey is not on AAII.com yet. Checking again ${formatEtInstant(next)}.`,
  };
}

async function writePoll(now: Date, latest: string | null, error: string | null, succeeded: boolean): Promise<PollState> {
  const previous = await readPollState();
  const next = nextCheckDate(now, latest);
  const described = describe(now, latest, next, error);
  const state: PollState = {
    lastAttemptAt: now.toISOString(),
    lastSuccessAt: succeeded ? now.toISOString() : previous.lastSuccessAt,
    latestReportedDate: latest,
    nextCheckAt: next.toISOString(),
    state: described.state,
    message: described.message,
    lastError: error,
  };
  await writeJson(POLL_FILE, state);
  return state;
}

export async function refreshAaii(): Promise<AaiiArchive> {
  const now = new Date();
  const existing = await readAaiiArchive();
  let pageHtml = "";
  let workbook: Buffer | null = null;
  let error: string | null = null;

  try {
    const page = await fetch(SURVEY_URL, {
      headers: BROWSER_HEADERS,
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
      redirect: "follow",
    });
    if (!page.ok) throw new Error(`Survey page returned ${page.status}`);
    pageHtml = await page.text();
    const cookies = cookieHeader(page);
    const sheet = await fetch(XLS_URL, {
      headers: { ...BROWSER_HEADERS, ...(cookies ? { Cookie: cookies } : {}) },
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
      redirect: "follow",
    });
    if (!sheet.ok) throw new Error(`Sentiment spreadsheet returned ${sheet.status}`);
    const bytes = Buffer.from(await sheet.arrayBuffer());
    if (bytes.length < 10_000 || bytes.subarray(0, 2).toString("utf8") === "<!") {
      throw new Error("Sentiment spreadsheet download was blocked");
    }
    workbook = bytes;
  } catch (cause) {
    error = cause instanceof Error ? cause.message : "AAII request failed";
  }

  const scraped = pageHtml ? parseAaiiChart(pageHtml) : null;
  let readings = existing.readings ?? [];
  let parsedWorkbook = false;
  if (workbook) {
    try {
      const incoming = parseSentimentWorkbook(workbook);
      if (incoming.length < 50) {
        error = error ?? "AAII spreadsheet parsed too few weeks";
      } else {
        readings = mergeReadings(readings, incoming);
        parsedWorkbook = true;
      }
    } catch (cause) {
      error = cause instanceof Error ? cause.message : "AAII spreadsheet could not be read";
    }
  }

  const derived = deriveAaiiChart(readings);
  let chart = existing.chart;
  let chartSource = existing.chartSource;
  if (scraped) {
    chart = scraped;
    chartSource = "aaii.com";
  } else if (parsedWorkbook && derived) {
    chart = derived;
    chartSource = "archive";
  } else if (!chart && derived) {
    chart = derived;
    chartSource = "archive";
  }

  const latest = readings.length ? readings[readings.length - 1].date : null;
  const succeeded = parsedWorkbook || Boolean(scraped);

  if (!succeeded && readings.length === 0) {
    await writePoll(now, null, error, false);
    throw new Error(error ?? "AAII survey is unavailable");
  }

  const archive: AaiiArchive = {
    ...EMPTY_ARCHIVE,
    ...existing,
    notes: EMPTY_ARCHIVE.notes,
    source: XLS_URL,
    updatedAt: succeeded ? now.toISOString() : existing.updatedAt,
    readings,
    chart,
    chartSource,
  };
  await writeJson(FILE, archive);
  const poll = await writePoll(now, latest, succeeded ? null : error, succeeded);
  console.log(`[aaii] latest ${latest ?? "none"}, weeks ${readings.length}, next ${poll.nextCheckAt}, ${poll.state}`);
  return archive;
}

export function aaiiView(archive: AaiiArchive, poll: PollState): AaiiView {
  return {
    chart: archive.chart,
    chartSource: archive.chartSource,
    archivedCount: archive.readings?.length ?? 0,
    updatedAt: archive.updatedAt,
    status: {
      state: poll.state,
      message: poll.message,
      nextCheckAt: poll.nextCheckAt,
      lastSuccessAt: poll.lastSuccessAt,
    },
  };
}

export function aaiiCheckIsDue(poll: PollState, now = new Date()): boolean {
  if (!poll.nextCheckAt) return true;
  return now.getTime() >= Date.parse(poll.nextCheckAt);
}
