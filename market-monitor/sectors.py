"""Sector leadership from the SPDR sector ETFs on Yahoo Finance.

The latest daily bar is the live session price (Yahoo is typically about
15 minutes behind the tape), so the 1-day figure updates through the day.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf

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
    ("1 DAY PERFORMANCE", 1),
    ("1 WEEK PERFORMANCE", 5),
    ("1 MONTH PERFORMANCE", 21),
    ("3 MONTH PERFORMANCE", 63),
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
                series = raw[symbol]["Close"]
                columns[symbol] = series
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


def load_sectors() -> dict[str, Any]:
    symbols = [symbol for _, symbol in SECTORS]
    frame = _close_frame(symbols)
    periods = []
    for title, sessions in PERIODS:
        rows = []
        for name, symbol in SECTORS:
            if symbol not in frame.columns:
                continue
            change = _change(frame[symbol], sessions)
            if change is None:
                continue
            rows.append({"name": name, "symbol": symbol, "change": round(change, 2)})
        rows.sort(key=lambda row: row["change"], reverse=True)
        peak = max((abs(row["change"]) for row in rows), default=0.0)
        periods.append({"title": title, "scale": nice_scale(peak), "rows": rows})
    if not any(period["rows"] for period in periods):
        raise RuntimeError("Sector performance is unavailable")
    return {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "periods": periods,
    }
