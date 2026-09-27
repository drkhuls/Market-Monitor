from __future__ import annotations

import csv
import json
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent / "data"
SENTIMENT_CSV = DATA_DIR / "sentiment_data.csv"
CSV_FIELDS = ["date", "value", "source", "fetched_at"]

STOCKCHARTS_HTML = "https://stockcharts.com/freecharts/symbolsummary.html?s=!NAAIM"
STOCKCHARTS_JSON = "https://stockcharts.com/j-sum/sum?cmd=symsum&symbol=!NAAIM"
STOCKCHARTS_CHART = "https://stockcharts.com/h-sc/ui?s=!NAAIM"
MACROMICRO_HTML = (
    "https://en.macromicro.me/collections/9/us-stock-relative/447/us-naaim-exposure-index"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

NAAIM_MIN = -200.0
NAAIM_MAX = 200.0


class NaaimFetchError(RuntimeError):
    pass


def latest_thursday(today: date | None = None) -> date:
    today = today or date.today()
    return today - timedelta(days=(today.weekday() - 3) % 7)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _parse_number(raw: str | float | int | None) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value if NAAIM_MIN <= value <= NAAIM_MAX else None
    text = str(raw).strip().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    value = float(match.group(0))
    if not (NAAIM_MIN <= value <= NAAIM_MAX):
        return None
    return value


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text[:16] if fmt.endswith("%H:%M") else text, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        return date.fromisoformat(match.group(1))
    return None


def _valid_reading(value: float | None, as_of: date | None, source: str) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "date": (as_of or latest_thursday()).isoformat(),
        "value": round(float(value), 2),
        "source": source,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def scrape_stockcharts_html(session: requests.Session | None = None) -> dict[str, Any] | None:
    """Parse the public StockCharts !NAAIM summary page with BeautifulSoup."""
    session = session or _session()
    response = session.get(STOCKCHARTS_HTML, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    value = None
    as_of = None

    for selector in [".tile-last", ".last", "#last", "[data-last]", ".quote-last"]:
        node = soup.select_one(selector)
        if node:
            value = _parse_number(node.get_text(" ", strip=True))
            if value is not None:
                break

    if value is None:
        for label in soup.find_all(["th", "td", "div", "span", "dt"]):
            text = label.get_text(" ", strip=True).lower()
            if text in {"last", "last close", "close", "last price"}:
                sibling = label.find_next(["td", "dd", "span", "div"])
                if sibling:
                    value = _parse_number(sibling.get_text(" ", strip=True))
                    if value is not None:
                        break

    for node in soup.find_all("script"):
        blob = node.string or ""
        if "lastClose" not in blob and "last_close" not in blob and "!NAAIM" not in blob:
            continue
        close_match = re.search(r'"lastClose"\s*:\s*"?(?P<val>-?\d+(?:\.\d+)?)"?', blob)
        date_match = re.search(r'"latestTrade"\s*:\s*"(?P<dt>[^"]+)"', blob)
        if close_match:
            value = _parse_number(close_match.group("val"))
        if date_match:
            as_of = _parse_date(date_match.group("dt"))
        if value is not None:
            break

    return _valid_reading(value, as_of, "stockcharts_html")


def scrape_stockcharts_quote(session: requests.Session | None = None) -> dict[str, Any] | None:
    """Read the public StockCharts quote used by the !NAAIM tracking page."""
    session = session or _session()
    response = session.get(STOCKCHARTS_JSON, timeout=20)
    response.raise_for_status()
    payload = response.json()
    value = _parse_number(payload.get("lastClose") or payload.get("close"))
    as_of = _parse_date(payload.get("latestTrade") or payload.get("fundamentals", {}).get("date"))
    return _valid_reading(value, as_of, "stockcharts")


def scrape_macromicro_html(session: requests.Session | None = None) -> dict[str, Any] | None:
    """Parse MacroMicro's public NAAIM page when it is not Cloudflare-blocked."""
    session = session or _session()
    response = session.get(MACROMICRO_HTML, timeout=20)
    if response.status_code != 200:
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    value = None
    as_of = None

    for selector in [".stat-val", ".latest-value", ".chart-stat__value", "[data-latest]"]:
        node = soup.select_one(selector)
        if node:
            value = _parse_number(node.get_text(" ", strip=True))
            if value is not None:
                break

    if value is None:
        heading = soup.find(string=re.compile(r"NAAIM", re.I))
        if heading:
            nearby = heading.parent.get_text(" ", strip=True) if heading.parent else ""
            value = _parse_number(nearby)

    date_node = soup.find(string=re.compile(r"\d{4}-\d{2}-\d{2}"))
    if date_node:
        as_of = _parse_date(str(date_node))

    return _valid_reading(value, as_of, "macromicro")


def fetch_latest_naaim() -> dict[str, Any]:
    session = _session()
    errors: list[str] = []
    scrapers = (
        scrape_stockcharts_html,
        scrape_stockcharts_quote,
        scrape_macromicro_html,
    )
    for scraper in scrapers:
        try:
            reading = scraper(session)
        except Exception as exc:
            errors.append(f"{scraper.__name__}: {exc}")
            continue
        if reading:
            return reading
        errors.append(f"{scraper.__name__}: no value found")
    raise NaaimFetchError("Could not scrape NAAIM from public trackers. " + " | ".join(errors))


def load_sentiment_history(path: Path = SENTIMENT_CSV) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def latest_sentiment(path: Path = SENTIMENT_CSV) -> dict[str, Any] | None:
    rows = load_sentiment_history(path)
    if not rows:
        return None
    rows.sort(key=lambda row: (row.get("date") or "", row.get("fetched_at") or ""))
    return rows[-1]


def save_sentiment_reading(reading: dict[str, Any], path: Path = SENTIMENT_CSV) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = [row for row in load_sentiment_history(path) if row.get("date") != reading["date"]]
    rows.append(
        {
            "date": reading["date"],
            "value": f"{float(reading['value']):.2f}",
            "source": reading["source"],
            "fetched_at": reading["fetched_at"],
        }
    )
    rows.sort(key=lambda row: row["date"])
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return reading


def needs_weekly_refresh(path: Path = SENTIMENT_CSV, today: date | None = None) -> bool:
    today = today or date.today()
    this_thursday = latest_thursday(today)
    latest = latest_sentiment(path)
    if not latest:
        return True
    as_of = _parse_date(latest.get("date"))
    fetched_at = _parse_date((latest.get("fetched_at") or "")[:10])
    if as_of is None or as_of < this_thursday:
        return True
    # Thursday reprints sometimes land later in the day.
    if today == this_thursday and fetched_at is not None and fetched_at < this_thursday:
        return True
    return False


def refresh_sentiment(force: bool = False, path: Path = SENTIMENT_CSV) -> dict[str, Any]:
    if not force and not needs_weekly_refresh(path):
        latest = latest_sentiment(path)
        if latest:
            return latest
    reading = fetch_latest_naaim()
    return save_sentiment_reading(reading, path)


def reading_from_csv() -> dict[str, Any] | None:
    latest = latest_sentiment()
    if not latest:
        return None
    return {
        "value": float(latest["value"]),
        "as_of": latest.get("date"),
        "source": latest.get("source"),
        "fetched_at": latest.get("fetched_at"),
        "note": f"Auto-fetched from {latest.get('source')}",
    }


PUBLIC_TABLE_URL = "https://index.naaim.org/embeddable/table"
HISTORY_PATH = DATA_DIR / "naaim-history.json"
_ROW_PATTERN = re.compile(
    r"<tr>\s*<td>(\d{2}/\d{2}/\d{4})</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*<td[^>]*>([^<]*)</td>\s*<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*<td[^>]*>([^<]*)</td>\s*<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*</tr>",
    re.IGNORECASE,
)
_history_lock = threading.Lock()
_history_attempted = False


def _num(value: str) -> float:
    return float(value.replace(",", "").strip())


def _us_to_iso(value: str) -> str:
    month, day, year = value.split("/")
    return f"{year}-{month}-{day}"


def parse_public_table(html: str) -> list[dict[str, Any]]:
    readings: list[dict[str, Any]] = []
    for match in _ROW_PATTERN.finditer(html):
        readings.append(
            {
                "date": _us_to_iso(match.group(1)),
                "exposure": _num(match.group(2)),
                "mostBearish": _num(match.group(3)),
                "quartile1": _num(match.group(4)),
                "median": _num(match.group(5)),
                "quartile3": _num(match.group(6)),
                "mostBullish": _num(match.group(7)),
                "deviation": _num(match.group(8)),
                "source": "naaim.org",
            }
        )
    readings.sort(key=lambda row: row["date"])
    return readings


def load_naaim_history() -> list[dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    try:
        payload = json.loads(HISTORY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    readings = payload.get("readings") if isinstance(payload, dict) else None
    return list(readings) if isinstance(readings, list) else []


def _write_history(readings: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    readings = sorted(readings, key=lambda row: row["date"])
    payload = {
        "notes": (
            "Permanent archive of NAAIM Exposure Index readings. "
            "The monitor table shows only the last 12 months. "
            "Do not delete rows when they age off the table."
        ),
        "source": PUBLIC_TABLE_URL,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "readings": readings,
    }
    temp = HISTORY_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2))
    temp.replace(HISTORY_PATH)


def backfill_naaim_history(force: bool = False) -> list[dict[str, Any]]:
    """Merge the public NAAIM table into the archive. Never drops old weeks."""
    global _history_attempted
    with _history_lock:
        existing = load_naaim_history()
        if existing and not force and _history_attempted:
            return existing
        _history_attempted = True
        try:
            response = requests.get(PUBLIC_TABLE_URL, headers=HEADERS, timeout=20)
            response.raise_for_status()
            incoming = parse_public_table(response.text)
        except Exception:
            return existing
        if len(incoming) < 20:
            return existing
        by_date = {row["date"]: row for row in existing}
        for row in incoming:
            previous = by_date.get(row["date"])
            if previous and previous.get("source") in {"stockcharts", "manual", "macromicro"}:
                continue
            by_date[row["date"]] = row
        merged = sorted(by_date.values(), key=lambda row: row["date"])
        if merged != existing:
            _write_history(merged)
        return merged


def naaim_year_rows(today: date | None = None) -> list[dict[str, Any]]:
    """Last 365 days, newest first. Older weeks stay in the archive files."""
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    cutoff = (today - timedelta(days=365)).isoformat()
    points: dict[str, float] = {}
    for reading in load_naaim_history():
        try:
            points[str(reading["date"])] = float(reading["exposure"])
        except (KeyError, TypeError, ValueError):
            continue
    for row in load_sentiment_history():
        source = row.get("source") or ""
        if source in {"stockcharts", "manual", "macromicro"} or row["date"] not in points:
            points[row["date"]] = float(row["value"])
    ordered = sorted(points)
    change_by_date: dict[str, float | None] = {}
    previous: str | None = None
    for day in ordered:
        if previous is None:
            change_by_date[day] = None
        else:
            change_by_date[day] = round(points[day] - points[previous], 2)
        previous = day
    visible = [day for day in ordered if day >= cutoff]
    visible.reverse()
    return [
        {"date": day, "exposure": points[day], "change": change_by_date[day]}
        for day in visible
    ]


if __name__ == "__main__":
    result = refresh_sentiment(force=True)
    print(json.dumps(result, indent=2))
    print(f"Saved to {SENTIMENT_CSV}")
    history = backfill_naaim_history(force=True)
    print(f"History weeks: {len(history)}")
