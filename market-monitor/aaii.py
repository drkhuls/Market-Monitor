"""AAII Investor Sentiment Survey.

The weekly spreadsheet is the permanent archive. The bar chart is copied from
the survey page so the colors and numbers match AAII.com. On Thursday at
10:00 AM Eastern the monitor looks for the new release. If it is not up yet,
it checks again every two hours.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
import xlrd

DATA_DIR = Path(__file__).resolve().parent / "data"
HISTORY_PATH = DATA_DIR / "aaii-history.json"
POLL_PATH = DATA_DIR / "aaii-poll.json"
SURVEY_URL = "https://www.aaii.com/sentimentsurvey"
XLS_URL = "https://www.aaii.com/files/surveys/sentiment.xls"
ET = ZoneInfo("America/New_York")
TWO_HOURS = timedelta(hours=2)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_lock = threading.Lock()
_started = False


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return dict(default)
    return payload if isinstance(payload, dict) else dict(default)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2))
    temp.replace(path)


def load_archive() -> dict[str, Any]:
    archive = _read_json(
        HISTORY_PATH,
        {
            "notes": "Permanent archive of the AAII Investor Sentiment Survey.",
            "source": XLS_URL,
            "updatedAt": None,
            "readings": [],
            "chart": None,
            "chartSource": None,
        },
    )
    archive.setdefault("readings", [])
    archive.setdefault("chart", None)
    return archive


def load_poll() -> dict[str, Any]:
    return _read_json(
        POLL_PATH,
        {
            "lastAttemptAt": None,
            "lastSuccessAt": None,
            "latestReportedDate": None,
            "nextCheckAt": None,
            "state": "empty",
            "message": "The AAII survey has not been collected yet.",
            "lastError": None,
        },
    )


def _round1(value: float) -> float:
    return round(float(value) + 1e-9, 1)


def _percent_in(chunk: str, kind: str) -> float | None:
    match = re.search(rf'class="bar {kind}"[^>]*>([\d.]+)%', chunk)
    return float(match.group(1)) if match else None


def parse_aaii_chart(html: str) -> dict[str, Any] | None:
    start = html.find("Recent weekly results")
    if start < 0:
        return None
    end = html.find("More Historical", start)
    section = html[start : end if end != -1 else start + 30_000]
    chunks = re.split(r'<div class="date[^"]*">', section)[1:]
    recent: list[dict[str, Any]] = []
    averages = None
    highs: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        label = re.sub(r"<[^>]+>", "", chunk[: chunk.find("</div>")]).strip()
        if not label or label == "Week Ending":
            continue
        ending_match = re.search(r'class="ending">([^<]+)', chunk)
        ending = ending_match.group(1).strip() if ending_match else ""
        bullish = _percent_in(chunk, "bullish")
        neutral = _percent_in(chunk, "neutral")
        bearish = _percent_in(chunk, "bearish")
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", label) and None not in (bullish, neutral, bearish):
            recent.append(
                {"weekEnding": label, "bullish": bullish, "neutral": neutral, "bearish": bearish}
            )
            continue
        if label == "Historical Averages" and None not in (bullish, neutral, bearish):
            averages = {"bullish": bullish, "neutral": neutral, "bearish": bearish}
            continue
        week_ending = re.sub(r"^Week Ending\s+", "", ending, flags=re.IGNORECASE)
        if label == "1-Year Bullish High" and bullish is not None and week_ending:
            highs["bullish"] = {"value": bullish, "weekEnding": week_ending}
        elif label == "1-Year Neutral High" and neutral is not None and week_ending:
            highs["neutral"] = {"value": neutral, "weekEnding": week_ending}
        elif label == "1-Year Bearish High" and bearish is not None and week_ending:
            highs["bearish"] = {"value": bearish, "weekEnding": week_ending}
    if averages is None or len(recent) < 4 or not all(k in highs for k in ("bullish", "neutral", "bearish")):
        return None
    return {"recent": recent, "averages": averages, "highs": highs}


def _week_ending_label(reported: str) -> str:
    year, month, day = (int(part) for part in reported.split("-"))
    previous = date(year, month, day) - timedelta(days=1)
    return f"{previous.month}/{previous.day}/{previous.year}"


def derive_chart(readings: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not readings:
        return None
    ordered = sorted(readings, key=lambda row: row["date"])
    recent = [
        {
            "weekEnding": _week_ending_label(row["date"]),
            "bullish": _round1(row["bullish"]),
            "neutral": _round1(row["neutral"]),
            "bearish": _round1(row["bearish"]),
        }
        for row in ordered[-4:][::-1]
    ]
    count = len(ordered)
    averages = {
        "bullish": _round1(sum(row["bullish"] for row in ordered) / count),
        "neutral": _round1(sum(row["neutral"] for row in ordered) / count),
        "bearish": _round1(sum(row["bearish"] for row in ordered) / count),
    }
    latest = date.fromisoformat(ordered[-1]["date"])
    cutoff = (latest - timedelta(days=365)).isoformat()
    year = [row for row in ordered if row["date"] >= cutoff] or ordered
    bullish = max(year, key=lambda row: row["bullish"])
    neutral = max(year, key=lambda row: row["neutral"])
    bearish = max(year, key=lambda row: row["bearish"])
    return {
        "recent": recent,
        "averages": averages,
        "highs": {
            "bullish": {"value": _round1(bullish["bullish"]), "weekEnding": _week_ending_label(bullish["date"])},
            "neutral": {"value": _round1(neutral["neutral"]), "weekEnding": _week_ending_label(neutral["date"])},
            "bearish": {"value": _round1(bearish["bearish"]), "weekEnding": _week_ending_label(bearish["date"])},
        },
    }


def parse_sentiment_workbook(content: bytes) -> list[dict[str, Any]]:
    book = xlrd.open_workbook(file_contents=content)
    try:
        sheet = book.sheet_by_name("SENTIMENT")
    except xlrd.XLRDError as exc:
        raise ValueError("AAII workbook is missing the SENTIMENT sheet") from exc
    readings: list[dict[str, Any]] = []
    for row_index in range(sheet.nrows):
        serial = sheet.cell_value(row_index, 0)
        if not isinstance(serial, (int, float)) or serial < 30_000:
            continue
        bullish = sheet.cell_value(row_index, 1)
        neutral = sheet.cell_value(row_index, 2)
        bearish = sheet.cell_value(row_index, 3)
        if not all(isinstance(value, (int, float)) for value in (bullish, neutral, bearish)):
            continue
        if bullish <= 0 and neutral <= 0 and bearish <= 0:
            continue
        reported = xlrd.xldate_as_datetime(serial, book.datemode).date().isoformat()
        readings.append(
            {
                "date": reported,
                "bullish": round(float(bullish) * 100, 4),
                "neutral": round(float(neutral) * 100, 4),
                "bearish": round(float(bearish) * 100, 4),
            }
        )
    readings.sort(key=lambda row: row["date"])
    return readings


def expected_reported_date(now: datetime | None = None) -> date:
    local = (now or datetime.now(timezone.utc)).astimezone(ET)
    day = local.date()
    if local.weekday() == 3 and local.hour < 10:
        day -= timedelta(days=1)
    back = (day.weekday() - 3) % 7
    return day - timedelta(days=back)


def thursday_at_ten(day: date) -> datetime:
    for offset_hours in (4, 5, 6):
        utc = datetime(day.year, day.month, day.day, 10 + offset_hours, 0, tzinfo=timezone.utc)
        local = utc.astimezone(ET)
        if local.date() == day and local.hour == 10 and local.minute == 0:
            return utc
    return datetime(day.year, day.month, day.day, 15, 0, tzinfo=timezone.utc)


def _format_long(day: date) -> str:
    return f"{day.strftime('%B')} {day.day}, {day.year}"


def _format_et(moment: datetime) -> str:
    local = moment.astimezone(ET)
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{local.strftime('%a, %b')} {local.day}, {hour}:{local.strftime('%M %p')} ET"


def _next_check(now: datetime, latest: str | None) -> datetime:
    expected = expected_reported_date(now)
    if latest and latest >= expected.isoformat():
        return thursday_at_ten(expected + timedelta(days=7))
    release = thursday_at_ten(expected)
    if now < release:
        return release
    return now + TWO_HOURS


def _describe(now: datetime, latest: str | None, nxt: datetime, error: str | None) -> tuple[str, str]:
    if not latest and error:
        return "error", f"Couldn't reach AAII.com. {error} Trying again {_format_et(nxt)}."
    if not latest:
        return "empty", "The AAII survey has not been collected yet."
    expected = expected_reported_date(now).isoformat()
    if latest >= expected:
        released = date.fromisoformat(latest)
        return (
            "current",
            f"Survey is current through the {_format_long(released)} release. Next check {_format_et(nxt)}.",
        )
    if error:
        return "error", f"This week's survey is not on AAII.com yet. {error} Checking again {_format_et(nxt)}."
    return "retrying", f"This week's survey is not on AAII.com yet. Checking again {_format_et(nxt)}."


def check_is_due(poll: dict[str, Any] | None = None, now: datetime | None = None) -> bool:
    poll = poll if poll is not None else load_poll()
    now = now or datetime.now(timezone.utc)
    nxt = poll.get("nextCheckAt")
    if not nxt:
        return True
    try:
        due = datetime.fromisoformat(str(nxt).replace("Z", "+00:00"))
    except ValueError:
        return True
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return now >= due


def refresh_aaii(force: bool = False) -> dict[str, Any]:
    with _lock:
        now = datetime.now(timezone.utc)
        existing = load_archive()
        poll = load_poll()
        if not force and existing.get("readings") and existing.get("chart") and not check_is_due(poll, now):
            return existing

        page_html = ""
        workbook: bytes | None = None
        error: str | None = None
        try:
            session = requests.Session()
            session.headers.update(HEADERS)
            page = session.get(SURVEY_URL, timeout=25)
            page.raise_for_status()
            page_html = page.text
            sheet = session.get(XLS_URL, timeout=40)
            sheet.raise_for_status()
            content = sheet.content
            if len(content) < 10_000 or content[:2] == b"<!":
                raise RuntimeError("Sentiment spreadsheet download was blocked")
            workbook = content
        except Exception as exc:
            error = str(exc)

        scraped = parse_aaii_chart(page_html) if page_html else None
        readings = list(existing.get("readings") or [])
        parsed = False
        if workbook:
            try:
                incoming = parse_sentiment_workbook(workbook)
                if len(incoming) < 50:
                    error = error or "AAII spreadsheet parsed too few weeks"
                else:
                    by_date = {row["date"]: row for row in readings}
                    for row in incoming:
                        by_date[row["date"]] = row
                    readings = sorted(by_date.values(), key=lambda row: row["date"])
                    parsed = True
            except Exception as exc:
                error = str(exc)

        derived = derive_chart(readings)
        chart = existing.get("chart")
        chart_source = existing.get("chartSource")
        if scraped:
            chart = scraped
            chart_source = "aaii.com"
        elif parsed and derived:
            chart = derived
            chart_source = "archive"
        elif chart is None and derived:
            chart = derived
            chart_source = "archive"

        latest = readings[-1]["date"] if readings else None
        succeeded = parsed or bool(scraped)
        if not succeeded and not readings:
            nxt = _next_check(now, None)
            state, message = _describe(now, None, nxt, error)
            _write_json(
                POLL_PATH,
                {
                    "lastAttemptAt": now.isoformat(),
                    "lastSuccessAt": poll.get("lastSuccessAt"),
                    "latestReportedDate": None,
                    "nextCheckAt": nxt.isoformat(),
                    "state": state,
                    "message": message,
                    "lastError": error,
                },
            )
            raise RuntimeError(error or "AAII survey is unavailable")

        archive = {
            "notes": (
                "Permanent archive of the AAII Investor Sentiment Survey. "
                "Readings come from sentiment.xls. The chart is copied from the survey page. "
                "Do not delete old weeks."
            ),
            "source": XLS_URL,
            "updatedAt": now.isoformat() if succeeded else existing.get("updatedAt"),
            "readings": readings,
            "chart": chart,
            "chartSource": chart_source,
        }
        _write_json(HISTORY_PATH, archive)
        nxt = _next_check(now, latest)
        state, message = _describe(now, latest, nxt, None if succeeded else error)
        _write_json(
            POLL_PATH,
            {
                "lastAttemptAt": now.isoformat(),
                "lastSuccessAt": now.isoformat() if succeeded else poll.get("lastSuccessAt"),
                "latestReportedDate": latest,
                "nextCheckAt": nxt.isoformat(),
                "state": state,
                "message": message,
                "lastError": None if succeeded else error,
            },
        )
        return archive


def aaii_view() -> dict[str, Any]:
    archive = load_archive()
    poll = load_poll()
    return {
        "chart": archive.get("chart"),
        "chartSource": archive.get("chartSource"),
        "archivedCount": len(archive.get("readings") or []),
        "message": poll.get("message") or "",
        "state": poll.get("state") or "empty",
    }


def _poll_loop() -> None:
    while True:
        try:
            if check_is_due() or not load_archive().get("chart"):
                refresh_aaii(force=False)
        except Exception:
            pass
        time.sleep(60)


def ensure_poller() -> None:
    """Background Thursday check. Streamlit re-runs the page, so the thread lives here."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    thread = threading.Thread(target=_poll_loop, name="aaii-poll", daemon=True)
    thread.start()
