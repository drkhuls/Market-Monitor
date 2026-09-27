const ET = "America/New_York";

export type EtParts = {
  weekday: string;
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

export function etParts(date: Date): EtParts {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    weekday: "short",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const bag: Record<string, string> = {};
  for (const part of fmt.formatToParts(date)) bag[part.type] = part.value;
  let hour = Number(bag.hour);
  if (hour === 24) hour = 0;
  return {
    weekday: bag.weekday,
    year: Number(bag.year),
    month: Number(bag.month),
    day: Number(bag.day),
    hour,
    minute: Number(bag.minute),
  };
}

export function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function isoDate(year: number, month: number, day: number): string {
  return `${year}-${pad(month)}-${pad(day)}`;
}

export function addCalendarDays(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function todayIsoET(now = new Date()): string {
  const parts = etParts(now);
  return isoDate(parts.year, parts.month, parts.day);
}

/** UTC instant for a wall-clock time in America/New_York, including DST. */
export function etClockToUtc(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
): Date {
  for (const offsetHours of [4, 5, 6]) {
    const utc = new Date(Date.UTC(year, month - 1, day, hour + offsetHours, minute, 0));
    const parts = etParts(utc);
    if (
      parts.year === year &&
      parts.month === month &&
      parts.day === day &&
      parts.hour === hour &&
      parts.minute === minute
    ) {
      return utc;
    }
  }
  return new Date(Date.UTC(year, month - 1, day, hour + 5, minute, 0));
}

export function mostRecentThursday(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const back = (date.getUTCDay() - 4 + 7) % 7;
  date.setUTCDate(date.getUTCDate() - back);
  return date.toISOString().slice(0, 10);
}

/**
 * Reported date AAII should already have published.
 * The spreadsheet dates each release on Thursday. Before 10:00 AM ET on
 * Thursday, the expected release is still the previous Thursday.
 */
export function expectedAaiiReportedDate(now = new Date()): string {
  const parts = etParts(now);
  let iso = isoDate(parts.year, parts.month, parts.day);
  if (parts.weekday === "Thu" && parts.hour < 10) {
    iso = addCalendarDays(iso, -1);
  }
  return mostRecentThursday(iso);
}

export function thursdayAtTenEt(isoThursday: string): Date {
  const [year, month, day] = isoThursday.split("-").map(Number);
  return etClockToUtc(year, month, day, 10, 0);
}

export function formatEtInstant(date: Date): string {
  const formatted = new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
  return formatted.replace(/\bE[DS]T\b/, "ET");
}

export function formatLongDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, day)));
}

export function formatShortDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return `${month}/${day}/${year}`;
}

export function formatQuoteTime(iso: string): string {
  const formatted = new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(iso));
  return formatted.replace(/\bE[DS]T\b/, "ET");
}

export function formatTodayLabel(now = new Date()): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(now);
}
