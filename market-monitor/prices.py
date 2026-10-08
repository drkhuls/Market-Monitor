"""Fill a blank Yahoo daily bar with the live session quote.

Yahoo sometimes publishes today's daily row with volume and empty
open/high/low/close. The quote still has the session price, so the chart,
the SPY/QQQ card, and the watchlist use that instead of showing nan or
falling back to yesterday.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf


def session_quote(symbol: str) -> dict[str, float] | None:
    try:
        info = yf.Ticker(symbol).fast_info
        close = float(info["lastPrice"])
        if close != close or close <= 0:
            return None
        quote = {"close": close}
        for column, key in (("open", "open"), ("high", "dayHigh"), ("low", "dayLow")):
            value = float(info[key])
            quote[column] = close if value != value or value <= 0 else value
        return quote
    except Exception:
        return None


def repair_daily_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Replace a trailing all-NaN price bar, then drop any remaining empty closes."""
    if frame is None or frame.empty or "Close" not in frame.columns:
        return frame
    out = frame.copy()
    if pd.isna(out["Close"].iloc[-1]):
        quote = session_quote(symbol)
        if quote:
            idx = out.index[-1]
            out.loc[idx, "Close"] = quote["close"]
            for column, key in (("Open", "open"), ("High", "high"), ("Low", "low")):
                if column in out.columns:
                    out.loc[idx, column] = quote[key]
        else:
            out = out.iloc[:-1]
    return out.dropna(subset=["Close"])


def last_two_closes(series: pd.Series, symbol: str) -> tuple[float, float] | None:
    if series is None or series.empty:
        return None
    values = series.astype(float).copy()
    if pd.isna(values.iloc[-1]):
        quote = session_quote(symbol)
        if quote is None:
            values = values.dropna()
        else:
            values.iloc[-1] = quote["close"]
            values = values.dropna()
    else:
        values = values.dropna()
    if len(values) < 2:
        return None
    return float(values.iloc[-1]), float(values.iloc[-2])
