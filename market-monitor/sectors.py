"""Sector leadership from the Finviz sector groups page.

One-day, one-week, one-month, and three-month moves are the same figures
Finviz publishes for each sector (Change, Perf Week, Perf Month, Perf Quart).
If that page is unavailable, the bars fall back to the SPDR sector ETFs.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from prices import repair_daily_frame

FINVIZ_URL = "https://finviz.com/groups.ashx?g=sector&v=140"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html",
}

SECTORS = [
    ("Utilities", "XLU"),
    ("Consumer Cyclical", "XLY"),
    ("Consumer Defensive", "XLP"),
    ("Real Estate", "XLRE"),
    ("Industrials", "XLI"),
    ("Basic Materials", "XLB"),
    ("Energy", "XLE"),
    ("Financial", "XLF"),
    ("Technology", "XLK"),
    ("Communication Services", "XLC"),
    ("Healthcare", "XLV"),
]

PERIODS = [
    ("1 DAY PERFORMANCE", "Change", 1),
    ("1 WEEK PERFORMANCE", "Perf Week", 5),
    ("1 MONTH PERFORMANCE", "Perf Month", 21),
    ("3 MONTH PERFORMANCE", "Perf Quart", 63),
]


def nice_scale(max_abs: float) -> float:
    """Axis ceiling in percent, a bit above the largest bar."""
    if max_abs <= 0:
        return 1.0
    padded = max_abs * 1.08
    if padded <= 1:
        return 1.0
    if padded <= 12:
        return float(math.ceil(padded))
    return float(math.ceil(padded / 2) * 2)


def _parse_pct(text: str) -> float | None:
    cleaned = text.replace("%", "").replace(",", "").replace("−", "-").strip()
    if cleaned in {"", "-", "—"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _header_key(cells: list[str], label: str) -> int | None:
    wanted = label.lower()
    for index, cell in enumerate(cells):
        name = cell.lower()
        if name == wanted or name.startswith(wanted):
            return index
    return None


def fetch_finviz_sectors() -> list[dict[str, Any]]:
    response = requests.get(FINVIZ_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    table = None
    header: list[str] = []
    for candidate in soup.find_all("table"):
        rows = candidate.find_all("tr")
        if not rows:
            continue
        cells = [cell.get_text(" ", strip=True) for cell in rows[0].find_all(["td", "th"])]
        if _header_key(cells, "Name") is not None and _header_key(cells, "Change") is not None:
            table = rows
            header = cells
            break
    if table is None:
        raise RuntimeError("Finviz sector table was not on the page")
    name_at = _header_key(header, "Name")
    columns = []
    for title, label, _sessions in PERIODS:
        index = _header_key(header, label)
        if index is None:
            raise RuntimeError(f"Finviz table has no {label} column")
        columns.append((title, index))
    periods: dict[str, list[dict[str, Any]]] = {title: [] for title, _index in columns}
    for row in table[1:]:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) <= name_at:
            continue
        name = cells[name_at]
        if not name or name.lower() == "name":
            continue
        for title, index in columns:
            if index >= len(cells):
                continue
            change = _parse_pct(cells[index])
            if change is None:
                continue
            periods[title].append({"name": name, "symbol": "", "change": round(change, 2)})
    built = []
    for title, _label, _sessions in PERIODS:
        rows = sorted(periods[title], key=lambda item: item["change"], reverse=True)
        if len(rows) < 8:
            raise RuntimeError(f"Finviz returned too few sectors for {title}")
        peak = max(abs(row["change"]) for row in rows)
        built.append({"title": title, "scale": nice_scale(peak), "rows": rows})
    return built


def _close_frame(symbols: list[str]) -> pd.DataFrame:
    raw = yf.download(
        symbols,
        period="1y",
        interval="1d",
        auto_adjust=True,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError("No sector prices returned")
    columns = {}
    if isinstance(raw.columns, pd.MultiIndex):
        for symbol in symbols:
            if symbol in raw.columns.get_level_values(0):
                columns[symbol] = raw[symbol]["Close"].rename(symbol)
    else:
        columns[symbols[0]] = raw["Close"]
    frame = pd.DataFrame(columns).dropna(how="all")
    if frame.empty:
        raise RuntimeError("Sector prices were empty")
    return frame


def _change(series: pd.Series, sessions_back: int) -> float | None:
    closes = series.dropna()
    if len(closes) <= sessions_back:
        return None
    last = float(closes.iloc[-1])
    base = float(closes.iloc[-1 - sessions_back])
    if not base:
        return None
    return (last / base - 1.0) * 100.0


def _etf_fallback() -> list[dict[str, Any]]:
    symbols = [symbol for _, symbol in SECTORS]
    frame = _close_frame(symbols)
    repaired = {}
    for symbol in symbols:
        if symbol not in frame.columns:
            continue
        column = frame[[symbol]].rename(columns={symbol: "Close"})
        column = repair_daily_frame(column, symbol)
        repaired[symbol] = column["Close"]
    periods = []
    for title, _label, sessions in PERIODS:
        rows = []
        for name, symbol in SECTORS:
            series = repaired.get(symbol)
            if series is None:
                continue
            change = _change(series, sessions)
            if change is None:
                continue
            rows.append({"name": name, "symbol": symbol, "change": round(change, 2)})
        rows.sort(key=lambda row: row["change"], reverse=True)
        peak = max((abs(row["change"]) for row in rows), default=0.0)
        periods.append({"title": title, "scale": nice_scale(peak), "rows": rows})
    if not any(period["rows"] for period in periods):
        raise RuntimeError("Sector performance is unavailable")
    return periods


def load_sectors() -> dict[str, Any]:
    error = None
    try:
        periods = fetch_finviz_sectors()
        source = "finviz"
    except Exception as exc:
        error = str(exc)
        periods = _etf_fallback()
        source = "yahoo"
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "periods": periods,
    }
    if error and source == "yahoo":
        payload["error"] = error
    return payload
